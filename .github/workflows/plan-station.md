---
on:
  workflow_dispatch:
    inputs:
      issue:
        description: Issue number to plan
        required: true
permissions:
  contents: read
  issues: read
engine: claude
safe-outputs:
  add-comment:
    target: "*"
  add-labels:
    allowed: [planning, "awaiting plan approval", "stopped: needs a fix"]
    target: "*"
  update-project:
    project: https://github.com/users/andre-siqueira-skan/projects/1
    github-token: ${{ secrets.PROJECT_TOKEN }}
---

# Plan station

You are the plan station of our software factory, working on issue #${{ github.event.inputs.issue }}
of this repository (a small FastAPI pet store with a docker compose stack).

1. Read the issue and the code it touches.
2. Write a short plan: files to change, tests that prove it, risks.
3. Post the plan as a comment on the issue.
4. Set the issue's card on the user project "Factory Lab" (number 1) to Status "Plan".
5. Add the label `awaiting plan approval`. If you cannot write a plan, add `stopped: needs a fix`
   and explain why in the comment.
