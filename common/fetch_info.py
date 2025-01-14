import requests
import os
import json
# from datetime import datetime
import dotenv
import psycopg2 # Ensure this import is at the top of your file
import datetime  # Ensure this import is at the top of your file

dotenv.load_dotenv("../credentials.env")

# GraphQL Query to fetch user ID dynamically
USER_QUERY = """
query GetUserByEmail($email: String!) {
    users(filter: {email: {eq: $email}}) {
        nodes {
            id
            name
            email
        }
    }
}
"""

# GraphQL Query to fetch issues associated with a user
ACTIVITIES_QUERY = """
query UserActivities($userId: ID!) {
    issues(filter: {assignee: {id: {eq: $userId}}}) {
        nodes {
            id
            title
            updatedAt
            createdAt
            state {
                name
            }
            comments {
                nodes {
                    body
                    createdAt
                }
            }
        }
    }
}
"""

def fetch_linear_user_id(email, api_key, api_url):
    # Set up headers
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    # Variables for the query
    variables = {
        "email": email
    }

    # Make the request
    response = requests.post(api_url, headers=headers, json={"query": USER_QUERY, "variables": variables})

    # Check for errors
    if response.status_code != 200:
        print(f"Error fetching user ID: {response.status_code}, {response.text}")
        return None

    data = response.json()
    users = data.get("data", {}).get("users", {}).get("nodes", [])
    if not users:
        print("No user found with the provided email.")
        return None

    return users[0]["id"]  # Return the first user's ID

def filter_linear_issues(issues, target_date):
    """
    Filter all the Linear issues based on the target date.
    """
    filtered_issues = []
    target_date_obj = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()

    for issue in issues:
        issue_date = datetime.datetime.fromisoformat(issue['createdAt'].replace("Z", "+00:00")).date()
        if issue_date == target_date_obj:
            filtered_issues.append(issue)

    return filtered_issues

def fetch_linear_user_activities(user_id, api_key, api_url, target_date=None):
    # Set up headers
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }

    # Variables for the query
    variables = {
        "userId": user_id
    }

    # Make the request
    response = requests.post(api_url, headers=headers, json={"query": ACTIVITIES_QUERY, "variables": variables})

    # Check for errors
    if response.status_code != 200:
        print(f"Error fetching user activities: {response.status_code}, {response.text}")
        return None

    data = response.json()
    issues = data.get("data", {}).get("issues", {}).get("nodes", [])

    if target_date:
        issues = filter_linear_issues(issues, target_date)

    return issues

def fetch_github_events(username: str, target_date: str) -> str:  
    """  
    Fetch GitHub events for the user on the given date and return them as a human-readable string.  
    """    
    url = f"https://api.github.com/users/{username}/events/public"  
    response = requests.get(url)  
    if response.status_code != 200:  
        print(f"Error: Received status code {response.status_code}")  
        raise ValueError(f"Error: Received status code {response.status_code}")  
  
    events = response.json() 
    filtered_events = [  
        event for event in events  
        if datetime.datetime.fromisoformat(event['created_at'].replace("Z", "+00:00")).date() == datetime.datetime.strptime(target_date, "%Y-%m-%d").date()  
    ]  
  
    # Process events and extract details  
    event_details = []  
    for event in filtered_events:  
        event_type = event['type']  
        repo_name = event['repo']['name']  
        event_date = datetime.datetime.fromisoformat(event['created_at'].replace("Z", "+00:00")).strftime('%Y-%m-%d %H:%M:%S')  
  
        details = f"Event Type: {event_type}\nRepository: {repo_name}\nDate: {event_date}"  
        # Event-specific details  
        if event_type == "PullRequestEvent":  
            pr_details = event['payload']['pull_request']  
            details += f"""  
                Action: {event['payload']['action']}  
                Pull Request URL: {pr_details['html_url']}  
                Title: {pr_details['title']}  
                Body: {pr_details['body']}  
            """  
        elif event_type == "PushEvent":  
            commits = event['payload']['commits']  
            commit_details = "\n".join(  
                f"  - Message: {commit['message']}\n    URL: {commit['url']}"  
                for commit in commits  
            )  
            details += f"\nCommits:\n{commit_details}"  
        elif event_type == "DeleteEvent":  
            details += f"""  
                Ref Type: {event['payload']['ref_type']}  
                Ref: {event['payload']['ref']}  
            """  
        elif event_type == "IssueCommentEvent":  
            comment_details = event['payload']['comment']  
            details += f"""  
                Action: {event['payload']['action']}  
                Issue URL: {event['payload']['issue']['html_url']}  
                Comment: {comment_details['body']}  
            """  
        elif event_type == "IssuesEvent":  
            issue_details = event['payload']['issue']  
            details += f"""  
                Action: {event['payload']['action']}  
                Issue URL: {issue_details['html_url']}  
                Title: {issue_details['title']}  
                Body: {issue_details['body']}  
            """  
        elif event_type == "CreateEvent":  
            details += f"""  
                Ref Type: {event['payload']['ref_type']}  
                Ref: {event['payload'].get('ref', "N/A")}  
            """  
  
        event_details.append(details)  
  
    # Combine all events into a single formatted string  
    return "\n\n".join(event_details)

def fetch_github_and_linear_events(user_email, github_username, api_key, api_url, target_date):
    # Fetch Linear user ID
    user_id = fetch_linear_user_id(user_email, api_key, api_url)
    if not user_id:
        print("Failed to retrieve Linear user ID.")
        return "Failed to retrieve Linear user ID."

    # Fetch Linear activities
    linear_activities = fetch_linear_user_activities(user_id, api_key, api_url, target_date)
    if not linear_activities:
        print("No Linear activities found.")
        linear_activities = []

    # Fetch GitHub events
    github_events = fetch_github_events(github_username, target_date)
    if not github_events:
        print("No GitHub events found.")
        github_events = ""

    # Combine results into a string
    combined_events = f"Linear Activities:\n{json.dumps(linear_activities, indent=2)}\n\nGitHub Events:\n{github_events}"

    return combined_events

def fetch_last_sql_update(username):
    """
    Fetch the last row (most recent date) for a given user from the dailypulse table.
    Return the result as a string with column names and values in a key-value pair format.
    """
    # Database connection parameters
    db_name = "dailypulse"
    db_user = "postgres"
    db_password = "admin"
    db_host = "localhost"
    db_port = "5432"

    # Connect to the database
    conn = psycopg2.connect(
        dbname=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port
    )

    try:
        with conn.cursor() as cursor:
            # SQL query to fetch the last row for the given user
            query = """
            SELECT * FROM dailypulse WHERE username = %s ORDER BY date DESC LIMIT 1;
            """
            cursor.execute(query, (username,))
            result = cursor.fetchone()

            if result:
                # Fetch column names
                colnames = [desc[0] for desc in cursor.description]
                # Combine column names and values into a dictionary
                result_dict = dict(zip(colnames, result))
                
                # Convert date objects to strings
                for key, value in result_dict.items():
                    if isinstance(value, (datetime.date, datetime.datetime)):
                        result_dict[key] = value.isoformat()
                
                # Convert the dictionary to a string format
                return json.dumps(result_dict, indent=2)
            else:
                print(f"No records found for user: {username}")
                return "No records found for user: {username}"
    except Exception as e:
        print(f"Error fetching last SQL update: {e}")
        return f"Error fetching last SQL update: {e}"
    finally:
        conn.close()

def main():
    USERNAME = os.getenv("GITHUB_USERNAME")  # Assuming the username is stored in the environment variable

    # Fetch the last SQL update
    last_sql_update = fetch_last_sql_update(USERNAME)
    if last_sql_update:
        print(last_sql_update)
    else:
        print("Failed to fetch the last SQL update.")

if __name__ == "__main__":
    main()