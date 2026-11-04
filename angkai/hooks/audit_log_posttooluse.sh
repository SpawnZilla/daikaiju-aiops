#!/bin/bash
# audit_log_posttooluse.sh - Post-tool-use audit logging hook
# This script implements the audit logging requirements from Section 11 of the Brief
#  (2026-09-19): tool_response is NOT always an object. MCP tools can
# return an array or a plain string; the original `.tool_response.success`
# then errored inside jq, LOG_ENTRY came out empty, and a blank line was
# appended instead of a record (confirmed against a real runner-launched
# session: 4 tool calls -> 4 blank lines). Every lookup below is now
# guarded by the response's type, and a record is ALWAYS one valid JSON line.
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "default"' 2>/dev/null)
[ -z "$SESSION_ID" ] && SESSION_ID="default"
# : extract raw tool output content for post-hoc fabrication detection.
# Truncated to 500 chars to bound log growth.
OUTPUT_CONTENT=$(echo "$INPUT" | jq -r '
  .tool_response as $r
  | if ($r | type) == "object" then
      (($r.stdout // $r.content // $r.file // $r.text // $r.output // "")
        | if type == "string" then . else tojson end)
    elif ($r | type) == "array" then
      ($r | map(if type == "object" then (.text // tojson) else tostring end) | join("\n"))
    elif ($r | type) == "string" then $r
    else "" end' 2>/dev/null | cut -c1-500)
OUTPUT_FIELD_USED=$(echo "$INPUT" | jq -r '
  .tool_response as $r
  | if ($r | type) == "object" then
      (if $r.stdout != null then "stdout"
       elif $r.content != null then "content"
       elif $r.file != null then "file"
       elif $r.text != null then "text"
       elif $r.output != null then "output"
       else "unmapped" end)
    elif ($r | type) == "array" then "array"
    elif ($r | type) == "string" then "string"
    else "unmapped" end' 2>/dev/null)
[ -z "$OUTPUT_FIELD_USED" ] && OUTPUT_FIELD_USED="unmapped"
SUCCESS=$(echo "$INPUT" | jq -c '(.tool_response | if type == "object" then .success else null end)' 2>/dev/null)
[ -z "$SUCCESS" ] && SUCCESS="null"
# Create audit log entry with proper JSON escaping using jq, compact (-c) for true JSONL
LOG_ENTRY=$(jq -nc --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  --arg sid "$SESSION_ID" \
  --arg tool "$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)" \
  --arg fp "$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty' 2>/dev/null)" \
  --arg cmd "$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)" \
  --argjson success "$SUCCESS" \
  --arg outcontent "$OUTPUT_CONTENT" \
  --arg outfield "$OUTPUT_FIELD_USED" \
  '{timestamp:$ts, session_id:$sid, tool_name:$tool, file_path:$fp, command:$cmd, success:$success, output_content:$outcontent, output_field_used:$outfield}' 2>/dev/null)
# Never append a blank line: if the record still failed to build, log a minimal marker
if [ -z "$LOG_ENTRY" ]; then
  LOG_ENTRY=$(jq -nc --arg ts "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" --arg sid "$SESSION_ID" \
    '{timestamp:$ts, session_id:$sid, tool_name:"", file_path:"", command:"", success:null, output_content:"", output_field_used:"record_build_failed"}')
fi
# Log file for audit trail
AUDIT_LOG="/srv/angkai/.claude/hooks/audit_log_posttooluse_${SESSION_ID}.log"
# Append to audit log
echo "$LOG_ENTRY" >> "$AUDIT_LOG" 2>/dev/null
# Also write to stdout for immediate visibility
echo "$LOG_ENTRY"
exit 0
