"""Board rules of our factory, played with plain gh calls (phase 0, no model).

Card moves use PROJECT_TOKEN (GITHUB_TOKEN cannot write a user-owned board).
Labels and comments use GH_TOKEN (the workflow's GITHUB_TOKEN), so they do not
trigger other workflows.
"""

import json
import os
import re
import subprocess
import sys

OWNER, NAME = os.environ["GITHUB_REPOSITORY"].split("/")
PROJECT_NUMBER = int(os.environ.get("PROJECT_NUMBER", "1"))
MARKER = re.compile(r"<!-- factory-status: (.+?) -->")
# Lanes only the factory may move a card into.
FACTORY_LANES = {"Plan", "Implementation", "PR Review", "QA", "Done"}


def gh(*args: str, project: bool = False) -> str:
    env = dict(os.environ)
    if project:
        env["GH_TOKEN"] = os.environ["PROJECT_TOKEN"]
    result = subprocess.run(["gh", *args], env=env, capture_output=True, text=True)
    if result.returncode:
        sys.exit(f"gh {args[0]} {args[1]} failed: {result.stderr.strip()}")
    return result.stdout


def graphql(query: str, **variables) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
    return json.loads(gh(*args, project=True))["data"]


def project() -> dict:
    data = graphql(
        """query($login:String!,$n:Int!){user(login:$login){projectV2(number:$n){id
        field(name:"Status"){... on ProjectV2SingleSelectField{id options{id name}}}}}}""",
        login=OWNER,
        n=PROJECT_NUMBER,
    )["user"]["projectV2"]
    options = {o["name"]: o["id"] for o in data["field"]["options"]}
    return {"id": data["id"], "field": data["field"]["id"], "options": options}


def card(issue: int, proj: dict) -> dict | None:
    data = graphql(
        """query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n){id
        projectItems(first:10){nodes{id project{id}
        fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}""",
        o=OWNER,
        r=NAME,
        n=issue,
    )["repository"]["issue"]
    for node in data["projectItems"]["nodes"]:
        if node["project"]["id"] == proj["id"]:
            status = (node["fieldValueByName"] or {}).get("name")
            return {"item": node["id"], "issue_id": data["id"], "status": status}
    return {"item": None, "issue_id": data["id"], "status": None}


def set_status(issue: int, status: str, note: str = "") -> None:
    proj = project()
    current = card(issue, proj)
    item = current["item"]
    if item is None:
        item = graphql(
            """mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}""",
            p=proj["id"],
            c=current["issue_id"],
        )["addProjectV2ItemById"]["item"]["id"]
    graphql(
        """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){updateProjectV2ItemFieldValue(input:{projectId:$p,
        itemId:$i,fieldId:$f,value:{singleSelectOptionId:$o}}){projectV2Item{id}}}""",
        p=proj["id"],
        i=item,
        f=proj["field"],
        o=proj["options"][status],
    )
    comment(
        issue, f"factory: card moved to **{status}**. {note}\n<!-- factory-status: {status} -->"
    )


def labels(issue: int, add: list[str] = (), remove: list[str] = ()) -> None:
    args = ["issue", "edit", str(issue), "-R", f"{OWNER}/{NAME}"]
    for name in add:
        args += ["--add-label", name]
    for name in remove:
        args += ["--remove-label", name]
    if len(args) > 5:
        gh(*args)


def comment(issue: int, body: str) -> None:
    gh("issue", "comment", str(issue), "-R", f"{OWNER}/{NAME}", "--body", body)


def last_factory_status(issue: int) -> str | None:
    bodies = json.loads(
        gh("issue", "view", str(issue), "-R", f"{OWNER}/{NAME}", "--json", "comments")
    )
    found = [m.group(1) for c in bodies["comments"] for m in [MARKER.search(c["body"])] if m]
    return found[-1] if found else None


def decide(issue: int, issue_labels: list[str]) -> str:
    """Which station an `approved` label opens: plan, build, or ignore (our gate rule)."""
    status = card(issue, project())["status"]
    if status == "Proposal" and "planning" not in issue_labels:
        return "plan"
    if status == "Plan" and "awaiting plan approval" in issue_labels:
        return "build"
    return "ignore"


def reconcile() -> None:
    """Move back every card a person moved by hand into a factory-only lane."""
    proj = project()
    items = graphql(
        """query($login:String!,$n:Int!){user(login:$login){projectV2(number:$n){items(first:100){
        nodes{id content{... on Issue{number repository{nameWithOwner}}}
        fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}""",
        login=OWNER,
        n=PROJECT_NUMBER,
    )["user"]["projectV2"]["items"]["nodes"]
    for item in items:
        content = item.get("content") or {}
        if content.get("repository", {}).get("nameWithOwner") != f"{OWNER}/{NAME}":
            continue
        issue, status = content["number"], (item["fieldValueByName"] or {}).get("name")
        expected = last_factory_status(issue) or "Todo"
        if status != expected and (status in FACTORY_LANES or expected in FACTORY_LANES):
            graphql(
                """mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){updateProjectV2ItemFieldValue(input:{
                projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$o}}){projectV2Item{id}}}""",
                p=proj["id"],
                i=item["id"],
                f=proj["field"],
                o=proj["options"][expected],
            )
            comment(
                issue,
                f"factory: card was moved by hand to **{status}**; moved back to "
                f"**{expected}**. A hand-moved card approves nothing.",
            )
            print(f"#{issue}: {status} -> {expected}")


def main() -> None:
    cmd, *args = sys.argv[1:]
    if cmd == "status":
        set_status(int(args[0]), args[1], " ".join(args[2:]))
    elif cmd == "labels":
        issue, *ops = args
        labels(int(issue), [o[1:] for o in ops if o[0] == "+"], [o[1:] for o in ops if o[0] == "-"])
    elif cmd == "comment":
        comment(int(args[0]), " ".join(args[1:]))
    elif cmd == "decide":
        print(decide(int(args[0]), json.loads(args[1])))
    elif cmd == "reconcile":
        reconcile()
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
