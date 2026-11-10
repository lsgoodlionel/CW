#!/usr/bin/env bash
# 把 Issue / PR 的状态同步到 GitHub Project「CW 开发与发布」的执行看板。
#
# 用法:scripts/project-sync.sh <issue|pr> <编号> <动作>
#   issue 动作:opened | assigned | reopened | closed
#   pr    动作:opened | reopened | ready_for_review | converted_to_draft | closed
# 环境变量:
#   GH_TOKEN         需含 Project 读写权限(Actions 中来自密钥 PROJECT_TOKEN)
#   REPO             owner/name,默认 lsgoodlionel/CW
#   PROJECT_OWNER    默认 lsgoodlionel;PROJECT_NUMBER 默认 2
#   DRY_RUN=1        只打印将要做的改动,不写入
set -euo pipefail

KIND=${1:?kind}; NUM=${2:?number}; ACTION=${3:?action}
REPO=${REPO:-lsgoodlionel/CW}
OWNER=${PROJECT_OWNER:-lsgoodlionel}
PNUM=${PROJECT_NUMBER:-2}
DRY=${DRY_RUN:-0}
R_OWNER=${REPO%%/*}; R_NAME=${REPO#*/}

log() { echo "[project-sync] $*"; }

# ---- Project 与字段(Status / 优先级)----
fields_query='query($o:String!,$n:Int!){ user(login:$o){ projectV2(number:$n){ id
  fields(first:50){ nodes{ ... on ProjectV2SingleSelectField{ id name options{ id name } } } } } } }'
project_jq() { gh api graphql -f query="$fields_query" -f o="$OWNER" -F n="$PNUM" --jq "$1"; }
PID=$(project_jq .data.user.projectV2.id)
field_id()  { project_jq ".data.user.projectV2.fields.nodes[] | select(.name==\"$1\") | .id"; }
option_id() { project_jq ".data.user.projectV2.fields.nodes[] | select(.name==\"$1\") | .options[] | select(.name==\"$2\") | .id"; }

STATUS_FIELD=$(field_id Status)
PRIO_FIELD=$(field_id 优先级)

# ---- 内容与其项目条目 ----
content_query='
  query($o:String!,$r:String!,$n:Int!){ repository(owner:$o,name:$r){ issueOrPullRequest(number:$n){
    __typename
    ... on Issue{ id state labels(first:20){ nodes{ name } }
      projectItems(first:20){ nodes{ id project{ id } fieldValueByName(name:"Status"){ ... on ProjectV2ItemFieldSingleSelectValue{ name } } } } }
    ... on PullRequest{ id state merged isDraft
      closingIssuesReferences(first:20){ nodes{ number } } } } } }'

content_field() {  # 编号 jq 表达式
  gh api graphql -f query="$content_query" -f o="$R_OWNER" -f r="$R_NAME" -F n="$1" \
    --jq ".data.repository.issueOrPullRequest | $2"
}

add_item() {  # 内容节点 id → 项目条目 id(已在项目中则返回原条目)
  if [ "$DRY" = 1 ]; then echo "DRY-ITEM-$1"; return; fi
  gh api graphql -f query='mutation($p:ID!,$c:ID!){ addProjectV2ItemById(input:{projectId:$p,contentId:$c}){ item{ id } } }' \
    -f p="$PID" -f c="$1" --jq .data.addProjectV2ItemById.item.id
}

set_select() {  # 条目 字段名 字段id 选项名
  local opt; opt=$(option_id "$2" "$4")
  [ -z "$opt" ] && { log "跳过:字段「$2」没有选项「$4」"; return; }
  log "设置 $2 = $4($5)"
  [ "$DRY" = 1 ] && return
  gh api graphql -f query='mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){ updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$o}}){ projectV2Item{ id } } }' \
    -f p="$PID" -f i="$1" -f f="$3" -f o="$opt" >/dev/null
}

set_status() { set_select "$1" Status "$STATUS_FIELD" "$2" "$3"; }

issue_status_now() {  # Issue 在本项目中的当前 Status(不在项目中则为空)
  content_field "$1" ".projectItems.nodes[] | select(.project.id==\"$PID\") | .fieldValueByName.name // \"\""
}

sync_issue_status() {  # Issue 编号 目标状态 [仅当当前状态为…]
  local n=$1 target=$2 only=${3:-} cid item now
  cid=$(content_field "$n" .id)
  if [ -n "$only" ]; then
    now=$(issue_status_now "$n")
    if [ "$now" != "$only" ]; then log "#$n 当前为「${now:-未加入}」,不改为「$target」"; return; fi
  fi
  item=$(add_item "$cid")
  set_status "$item" "$target" "#$n"
}

case "$KIND:$ACTION" in
  issue:opened)
    cid=$(content_field "$NUM" .id); item=$(add_item "$cid")
    set_status "$item" 待办 "#$NUM"
    prio=$(content_field "$NUM" '[.labels.nodes[].name | select(test("^P[0-2]$"))][0] // ""')
    [ -n "$prio" ] && set_select "$item" 优先级 "$PRIO_FIELD" "$prio" "#$NUM"
    ;;
  issue:assigned|issue:reopened)
    sync_issue_status "$NUM" 开发中 ;;
  issue:closed)
    sync_issue_status "$NUM" 完成 ;;
  pr:opened|pr:reopened|pr:ready_for_review|pr:converted_to_draft)
    cid=$(content_field "$NUM" .id); item=$(add_item "$cid")
    if [ "$(content_field "$NUM" .isDraft)" = true ]; then st=开发中; else st=验收中; fi
    set_status "$item" "$st" "PR #$NUM"
    for n in $(content_field "$NUM" '.closingIssuesReferences.nodes[].number'); do
      sync_issue_status "$n" "$st"
    done
    ;;
  pr:closed)
    cid=$(content_field "$NUM" .id); linked=$(content_field "$NUM" '.closingIssuesReferences.nodes[].number')
    if [ "$(content_field "$NUM" .merged)" = true ]; then
      item=$(add_item "$cid"); set_status "$item" 完成 "PR #$NUM"
      for n in $linked; do sync_issue_status "$n" 完成; done
    else
      item=$(add_item "$cid")
      log "PR #$NUM 未合并即关闭:从看板归档"
      [ "$DRY" = 1 ] || gh api graphql -f query='mutation($p:ID!,$i:ID!){ archiveProjectV2Item(input:{projectId:$p,itemId:$i}){ item{ id } } }' \
        -f p="$PID" -f i="$item" >/dev/null
      for n in $linked; do sync_issue_status "$n" 开发中 验收中; done
    fi
    ;;
  *)
    log "忽略:$KIND $ACTION" ;;
esac
log "完成:$KIND #$NUM $ACTION"
