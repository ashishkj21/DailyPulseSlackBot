from typing import Optional, Type  
import os  
from sqlalchemy.engine.url import URL  
from langchain.pydantic_v1 import BaseModel, Field, Extra  
from langchain.tools import BaseTool  
from langchain.sql_database import SQLDatabase  
from langchain_community.agent_toolkits import SQLDatabaseToolkit, create_sql_agent  
from langchain_openai import AzureChatOpenAI  
from langchain.callbacks.manager import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun   
from common.fetch_info import fetch_github_and_linear_events, fetch_last_sql_update
  
try:  
    from .prompts import MSSQL_AGENT_PREFIX  
except ImportError as e:  
    print(e)  
    from prompts import MSSQL_AGENT_PREFIX  
  
####################################################################################################################################  
# AGENTS AND TOOL CLASSES  
####################################################################################################################################  
  
class SearchInput(BaseModel):  
    query: str = Field(description="should be a search query")  
    return_direct: bool = Field(  
        description="Whether or the result of this should be returned directly to the user without you seeing what it is",  
        default=False,  
    )  
  
class SQLSearchAgent(BaseTool):  
    """Agent to interact with SQL database"""  
  
    name = "sqlsearch"  
    description = "useful when the questions includes the term: sqlsearch.\n"  
    args_schema: Type[BaseModel] = SearchInput  
    llm: AzureChatOpenAI  
    k: int = 10  
  
    class Config:  
        extra = Extra.allow  # Allows setting attributes not declared in the model  
  
    def __init__(self, **data):  
        super().__init__(**data)  
        db_config = self.get_db_config()  
        db_url = URL.create(**db_config)  
        db = SQLDatabase.from_uri(db_url, schema="public", view_support=True)  
        toolkit = SQLDatabaseToolkit(db=db, llm=self.llm)  
        self.agent_executor = create_sql_agent(  
            prefix=MSSQL_AGENT_PREFIX,  
            llm=self.llm,  
            toolkit=toolkit,  
            top_k=self.k,  
            agent_type="openai-tools",  
            callback_manager=self.callbacks,  
            verbose=self.verbose,  
        )  
  
    def get_db_config(self):  
        """Returns the database configuration."""  
        return {  
            'drivername': 'postgresql+psycopg2',  
            'username': os.environ["SQL_SERVER_USERNAME"],  
            'password': os.environ["SQL_SERVER_PASSWORD"],  
            'host': os.environ["SQL_SERVER_NAME"],  
            'port': 5432,  
            'database': os.environ["SQL_SERVER_DATABASE"]  
        }  
  
    def _run(self, query: str, return_direct=False, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:  
        try:  
            # Use the initialized agent_executor to invoke the query  
            result = self.agent_executor.invoke(query)  
            return result['output']  
        except Exception as e:  
            print(e)  
            return str(e)  # Return an error indicator  
  
    async def _arun(self, query: str, return_direct=False, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:  
        # Note: Implementation assumes the agent_executor and its methods support async operations  
        try:  
            # Use the initialized agent_executor to asynchronously invoke the query  
            result = await self.agent_executor.ainvoke(query)  
            return result['output']  
        except Exception as e:  
            print(e)  
            return str(e)  # Return an error indicator  
  
class Github_Linear_UpdateTool(BaseTool):  
    name = "github_linear_update"  
    description = "Fetches GitHub and Linear updates for the given username from the environment variable for yesterday's date"  
  
    def _run(self) -> str:  
        """Use the tool."""  
        print("Running Github_Linear_UpdateTool")  
        username = os.getenv("GITHUB_USERNAME")
        user_email = os.getenv("LINEAR_USER_EMAIL")
        api_key = os.getenv("LINEAR_API_KEY")
        api_url = os.getenv("LINEAR_API_URL")
        
        if not username:  
            print("Error: GITHUB_USERNAME environment variable is not set")  
            raise ValueError("GITHUB_USERNAME environment variable is not set")  
        if not user_email:
            print("Error: USER_EMAIL environment variable is not set")
            raise ValueError("USER_EMAIL environment variable is not set")
        if not api_key:
            print("Error: API_KEY environment variable is not set")
            raise ValueError("API_KEY environment variable is not set")
  
        # yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")  
        yesterday = "2025-01-13"
        print(f"Fetching GitHub and Linear events for user: {username} on date: {yesterday}")  
        events = fetch_github_and_linear_events(user_email, username, api_key, api_url, yesterday)  
        print(f"Fetched events: {events}")  
        return events  
  
class GetUpdateFromMemoryTool(BaseTool):
    name = "get_update_from_memory"
    description = "Fetches the last SQL update for the given username from the environment variable"

    def _run(self) -> str:
        """Use the tool."""
        print("Running GetUpdateFromMemoryTool")
        username = os.getenv("GITHUB_USERNAME")
        
        if not username:
            print("Error: GITHUB_USERNAME environment variable is not set")
            raise ValueError("GITHUB_USERNAME environment variable is not set")
        
        print(f"Fetching last SQL update for user: {username}")
        result = fetch_last_sql_update(username)
        print(f"Fetched result: {result}")
        return result  
  
  