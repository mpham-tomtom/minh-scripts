#!/usr/bin/env bash

# Usage:
# ./delete_orbit_issues_from_project.sh <bearer-token> <project-id>
#
# Arguments:
#   bearer-token  - Bearer token for API authentication
#   project-id    - The Orbit project ID to delete all issues from

BASE_URL="https://hapt-task-manager.tti-fdp.orbisplatform.com"
BEARER_TOKEN=$1
PROJECT_ID=$2

if [ -z "$BEARER_TOKEN" ] || [ -z "$PROJECT_ID" ]; then
  echo "Usage: $0 <bearer-token> <project-id>"
  exit 1
fi

echo "========================================"
echo "Deleting all issues from project: $PROJECT_ID"
echo "========================================"

PAGE_SIZE=10000
TOTAL_DELETED=0

while true; do
  echo ""
  echo "Fetching issues..."

  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer $BEARER_TOKEN" \
    "${BASE_URL}/orbit/api/v2/issues?projectId=${PROJECT_ID}&pageSize=${PAGE_SIZE}&pageNumber=0")

  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" -ne 200 ]; then
    echo "Error fetching issues: HTTP $HTTP_CODE"
    echo "$BODY"
    exit 1
  fi

  ISSUE_IDS=$(echo "$BODY" | jq -r '.issues[].id')
  ISSUE_COUNT=$(echo "$BODY" | jq '.issues | length')

  if [ "$ISSUE_COUNT" -eq 0 ]; then
    echo "No more issues found."
    break
  fi

  echo "Found $ISSUE_COUNT issues"

  for ISSUE_ID in $ISSUE_IDS; do
    DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE \
      -H "Authorization: Bearer $BEARER_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"issueId\": $ISSUE_ID, \"comment\": \"Bulk delete for project $PROJECT_ID\"}" \
      "${BASE_URL}/orbit/api/v1/issue")

    DELETE_HTTP_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)

    if [ "$DELETE_HTTP_CODE" -eq 200 ]; then
      echo "Deleted issue $ISSUE_ID"
      TOTAL_DELETED=$((TOTAL_DELETED + 1))
    else
      DELETE_BODY=$(echo "$DELETE_RESPONSE" | sed '$d')
      echo "Failed to delete issue $ISSUE_ID: HTTP $DELETE_HTTP_CODE - $DELETE_BODY"
    fi
  done

  # Always re-fetch page 0 since issues are being deleted
  # Only break when the page comes back empty
done

echo ""
echo "========================================"
echo "Deletion complete. Total deleted: $TOTAL_DELETED"
echo "========================================"
