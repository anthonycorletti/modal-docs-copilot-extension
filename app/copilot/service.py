import json
import re
import shutil
import tempfile
from typing import Dict, List

import httpx
import structlog
from bs4 import BeautifulSoup as BS
from bs4 import SoupStrainer
from httpx import URL
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, WebBaseLoader
from langchain_community.vectorstores import USearch
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableParallel, RunnablePassthrough
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.settings import settings

log = structlog.get_logger()


class CopilotService:
    """Data pipelines for scraping and storing data in usearch vector store to power
    the copilot extension app."""

    # TODO: add example code from github.com/modal-labs/modal-examples
    ROOT_URLS = [
        "https://modal.com/docs/guide",
        "https://modal.com/docs/examples",
        "https://modal.com/docs/reference",
    ]

    def get_content_urls(self, url: str) -> List[str]:
        result = []
        _url = URL(url)
        host = _url.host
        log.info(f"Getting content urls from {url}...")
        response = httpx.get(url)
        assert response.status_code == 200
        soup = BS(response.text, "html.parser")
        log.info(f"Scraping {url}...")
        article_links = soup.find_all("a", href=re.compile(f"{_url.path}"))
        log.info(f"Found {len(article_links)} article links...")
        relative_urls = [
            link["href"] for link in article_links if link["href"].startswith("/")
        ]
        log.info(f"Found {len(relative_urls)} relative urls...")
        log.info(f"First 10 relative urls: {relative_urls[:10]}")
        urls = [f"https://{host}{relative_url}" for relative_url in relative_urls]
        result.extend(urls)
        return result

    def load_urls_from_web(self, urls: List[str]) -> List[Document]:
        log.info(f"Loading {len(urls)} urls from the web...")
        loader = WebBaseLoader(
            web_paths=urls, bs_kwargs=dict(parse_only=SoupStrainer("main"))
        )
        return loader.load()

    def write_url_content_to_disk(self, docs: List[Document], path: str) -> None:
        with tempfile.NamedTemporaryFile("w") as temp_file:
            for doc in docs:
                temp_file.write("---------------------------\n")
                temp_file.write(json.dumps(doc.metadata))
                temp_file.write("\n")
                temp_file.write(doc.page_content.strip())
                temp_file.write("\n\n")
                temp_file_path = temp_file.name
            shutil.move(temp_file_path, path)

    def run_pipeline(self) -> None:
        urls: List[str] = []
        log.info("Starting pipeline...")
        log.info("Getting all urls...")
        for url in self.ROOT_URLS:
            urls.extend(self.get_content_urls(url))
        log.info(f"Scraping {len(urls)} urls...")
        log.info(f"First 10 urls: {urls[:10]}")
        docs = self.load_urls_from_web(urls)
        log.info(f"Writing {len(docs)} documents to disk...")
        # TODO: instead of writing all content to one file, write one file per url
        # will need to have multiple text loaders for that too
        self.write_url_content_to_disk(docs, settings.MODAL_CONTENT_PATH)
        log.info("Pipeline complete!")

    def load_modal_content_from_disk(self, path: str) -> List[Document]:
        loader = TextLoader(file_path=path)
        docs = loader.load()
        print(f"Loaded {len(docs)} documents from disk.")
        for i, doc in enumerate(docs):
            second_line = doc.page_content.split("\n")[1]
            json_parsed = json.loads(second_line)
            doc.metadata = {"source": json_parsed["source"]}
        return docs

    def split_documents(
        self,
        docs: List[Document],
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        add_start_index: bool = True,
    ) -> List[Document]:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            add_start_index=add_start_index,
        )
        return text_splitter.split_documents(docs)

    def retriever(
        self,
        user_query: str,
        splits: List[Document],
        search_type: str = "similarity",
        top_k: int = 6,
        model_name: str = "gpt-4-0125-preview",
        temperature: int = 0,
    ) -> str:
        vectorstore = USearch.from_documents(
            documents=splits,
            embedding=OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY),
        )
        search_kwargs = {"k": top_k}
        retriever = vectorstore.as_retriever(
            search_type=search_type, search_kwargs=search_kwargs
        )
        llm = ChatOpenAI(
            name=model_name, temperature=temperature, api_key=settings.OPENAI_API_KEY
        )

        template = """Use the following pieces of context to answer
        the question at the end with a clear, concise, and cogent answer.
        "If you don't know the answer, just say that you don't know, don't
        try to make up an answer and suggest the user ask their question in
        Modal's Community Slack Channel or to email support@modal.com.

        You are a helpful assistant that replies to user messages only in response
        to questions from the user about documentation on modal.com/docs. This includes
        but is not limited to: https://modal.com/docs/guide,
        https://modal.com/docs/examples,
        https://modal.com/docs/reference.

        {context}

        Question: {question}

        Answer:"""  # noqa E501

        def format_docs(docs: List[Document]) -> str:
            return "\n\n".join(doc.page_content for doc in docs)

        def format_to_markdown(data: Dict) -> str:
            markdown_output = f"{data['answer']}\n\nSources:\n\n"
            for i, doc in enumerate(data["context"], start=1):
                page_content = doc.page_content.split("\n")[0]
                source_link = doc.metadata["source"]
                markdown_output += f"[[{i}]({source_link})] {page_content}\n\n"
            return markdown_output

        prompt = PromptTemplate.from_template(template)
        rag_chain_from_docs = (
            RunnablePassthrough.assign(context=(lambda x: format_docs(x["context"])))
            | prompt
            | llm
            | StrOutputParser()
        )

        rag_chain_with_source = RunnableParallel(
            {"context": retriever, "question": RunnablePassthrough()}
        ).assign(answer=rag_chain_from_docs)

        chain_res = rag_chain_with_source.invoke(user_query)
        return format_to_markdown(chain_res)
