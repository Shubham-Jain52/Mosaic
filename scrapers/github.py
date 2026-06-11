"""
GitHub specific scraper.
"""
from requests import get
from dotenv import load_dotenv
import os
from core.models import PR_Structure,Review_Comment_Structure

load_dotenv()

TOKEN=os.getenv("GITHUB_TOKEN")

def fetch_PR_comments(pr_number:int,owner:str,repo:str):
    page = 1
    comments=[]
    while True:
        Target_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments?state=all&per_page=100&page={page}"
        response = get(Target_url, headers={
            "Authorization": f"Bearer {TOKEN}",
            "user-agent": "Mosaic-CLI"
        })
        if response.status_code != 200:
            print(f"Error fetching PR comments: {response.status_code}")
            return []
        comments_data = response.json()
        for comment in comments_data:
            clean_comment_data = Review_Comment_Structure(
                comment_id=comment.get("comment_id"),
                comment_body=comment.get("body"),
                diff_hunk=comment.get("diff_hunk"),
                file_path=comment.get("path"),
                author=comment.get("user").get("login")
            )
            comments.append(clean_comment_data)

        if len(comments_data) < 100:
            break
        page += 1
    return comments


def fetch_pull_requests(owner:str, repo:str):
    """
    Fetches all pull requests for a given repository.
    Returns a list of PR objects.
    """
    page = 1
    all_prs = []
    
    while True:
        # Request URL for pull requests
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&per_page=100&page={page}"
        
        response = get(url, headers={
            "Authorization": f"Bearer {TOKEN}",
            "user-agent": "Mosaic-CLI"
        })
        
    
        if response.status_code != 200:
            print(f"Error fetching PRs: {response.status_code}")
            return []
            
        prs = response.json()
        
        # If no PRs returned, we've reached the end
        if not prs:
            print("No PRs found")
            break
            
        for pr_data in prs:

            clean_Data = PR_Structure(
                number=pr_data.get("number"),
                title=pr_data.get("title"),
                state=pr_data.get("state"),
                description=pr_data.get("body"),
                comments=fetch_PR_comments(pr_data.get("number"),owner,repo)
            )
            all_prs.append(clean_Data)
        
        # Check if we got a full page (100 items). If not, this was the last page.
        if len(prs) < 100:
            break
            
        page += 1
        break
    return all_prs




DATA=fetch_pull_requests("tiangolo","fastapi")
# for pr in DATA:
#     if len(pr.comments) > 0:
#         print(f"BINGO! PR #{pr.number} has {len(pr.comments)} comments!")
#         print(pr.comments[0]) # Print the very first comment object
#         break

print(DATA[6])
# Example usage:
# owner = "Shubham-Jain52"
# repo = "mosaic"
# pull_requests = fetch_pull_requests(owner, repo)
# print(f"Found {len(pull_requests)} pull requests for {owner}/{repo}")
# for pr in pull_requests:
#     print(f"PR #{pr['number']}: {pr['title']} by {pr['user']['login']}")