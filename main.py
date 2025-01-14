import os
from fastapi import FastAPI, Request, HTTPException
from slack_bolt.adapter.fastapi import SlackRequestHandler
from slack_bolt import App
from dotenv import load_dotenv
import random
from langchain_openai import AzureChatOpenAI
from langchain.agents import AgentExecutor, Tool, create_openai_tools_agent
from langchain_community.chat_message_histories import CosmosDBChatMessageHistory
from langchain.callbacks.manager import CallbackManager
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import ConfigurableFieldSpec

#custom libraries that we will use later in the app
from common.utils import (
    SQLSearchAgent, 
    Github_Linear_UpdateTool
)
from common.callbacks import StdOutCallbackHandler
from common.prompts import CUSTOM_CHATBOT_PROMPT 

# Load environment variables from credentials.env file
load_dotenv("credentials.env")

# Set Slack API credentials
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

cb_handler = StdOutCallbackHandler()
cb_manager = CallbackManager(handlers=[cb_handler])

COMPLETION_TOKENS = 2000

# Initialize the Slack app
slack_app = App(token=SLACK_BOT_TOKEN)


llm = AzureChatOpenAI(deployment_name=os.environ["GPT4o_DEPLOYMENT_NAME"], temperature=0, max_tokens=COMPLETION_TOKENS, streaming=True, callback_manager=cb_manager, api_version="2024-05-01-preview")

sql_search = SQLSearchAgent(llm=llm, k=10, callback_manager=cb_manager,
                name="sqlsearch",
                description="useful when the questions includes the term: sqlsearch",
                verbose=False)

github_linear_update_tool = Github_Linear_UpdateTool(
    name="github_linear_update",
    description="Fetches GitHub and Linear updates for the given username from the environment variable for yesterday's date",
    verbose=False
)

tools = [sql_search, github_linear_update_tool]
agent = create_openai_tools_agent(llm, tools, CUSTOM_CHATBOT_PROMPT)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False)
# Initialize the FastAPI app
app = FastAPI()
handler = SlackRequestHandler(slack_app)

def get_session_history(session_id: str, user_id: str) -> CosmosDBChatMessageHistory:
    cosmos = CosmosDBChatMessageHistory(
        cosmos_endpoint=os.environ['AZURE_COSMOSDB_ENDPOINT'],
        cosmos_database=os.environ['AZURE_COSMOSDB_NAME'],
        cosmos_container=os.environ['AZURE_COSMOSDB_CONTAINER_NAME'],
        connection_string=os.environ['AZURE_COMOSDB_CONNECTION_STRING'],
        session_id=session_id,
        user_id=user_id
        )

    # prepare the cosmosdb instance
    cosmos.prepare_cosmos()
    return cosmos

brain_agent_executor = RunnableWithMessageHistory(
    agent_executor,
    get_session_history,
    input_messages_key="question",
    history_messages_key="history",
    history_factory_config=[
        ConfigurableFieldSpec(
            id="user_id",
            annotation=str,
            name="User ID",
            description="Unique identifier for the user.",
            default="",
            is_shared=True,
        ),
        ConfigurableFieldSpec(
            id="session_id",
            annotation=str,
            name="Session ID",
            description="Unique identifier for the conversation.",
            default="",
            is_shared=True,
        ),
    ],
)

# This is where we configure the session id and user id
random_session_id = "session"+ str(random.randint(1, 1000))
ramdom_user_id = "user"+ str(random.randint(1, 1000))
config={"configurable": {"session_id": random_session_id, "user_id": ramdom_user_id}}
print(random_session_id, ramdom_user_id)

def chat_with_agent(question):  
    response = brain_agent_executor.invoke({"question": question}, config=config)["output"]
    return response


@slack_app.event("app_mention")
def handle_mentions(event, say):
    """
    Event listener for mentions in Slack.
    Logs the event data when the bot is mentioned.
    """
    print("Mention event received:", event)
    say("Hello! I received your mention.")

@slack_app.event("message")
def handle_messages(event, say):
    """
    Event listener for messages in Slack.
    This function processes the text and sends a response based on the message type.

    Args:
        event (dict): The event data received from Slack.
        say (callable): A function for sending a response to the channel.
    """
    text = event["text"]
    channel_type = event.get("channel_type")

    if channel_type == "im":
        response = chat_with_agent(text)
        if response:
            say(response)
        else:
            say("Sorry, I didn't understand that. Can you please rephrase?")

@app.post("/slack/events")
async def slack_events(request: Request):
    """
    Route for handling Slack events.
    This function passes the incoming HTTP request to the SlackRequestHandler for processing.
    """
    try:
        return await handler.handle(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Run the app
# uvicorn main:app --reload --port 3000 