# 新发现最短复现（沙箱，main 4c71830e / 发布 1.3.3-163c7a3）

前置（隔离沙箱，宿主不受影响）：
```bash
rsync -a --exclude=.venv --exclude=.git --exclude='*.pyc' /workspace/ /tmp/drill-ws/
cd /tmp/drill-ws && git init -q && git add -A && git commit -qm baseline
PY=/workspace/.venv/bin/python; M="main.py"      # 在 /tmp/drill-ws 内执行
$PY main.py project create --stack python --id SW-2026-991 --name drill_py_fake2 --dest-dir /tmp/drill-ws/0100_项目 -bl SW
$PY main.py project create --stack plc --id SW-2026-992 --name drill_plc_fake2 --dest-dir /tmp/drill-ws/0100_项目 -bl SW --mode standard-project --plc-vendor Siemens --plc-model S7-1200
$PY main.py project register SW-2026-991
$PY main.py project register SW-2026-992
# 入箱/计划/批准/开工（详细参数见 transcript）
```

D1（P0 文档类需求死路）：
```bash
# scope 只有 README.md 的卡走到 VERIFYING 后
$PY main.py pm verify --mission-id <MISSION> --lease-wallet     # exit 1 自动 Checkpoint generic profile 无法验证: Run 缺少已批准的 owned Python path
$PY main.py pm accept --mission-id <MISSION>                     # exit 1 当前 Mission 尚未到达用户验收门
$PY main.py pm close  --mission-id <MISSION>                     # exit 1 该需求尚未验收，不能收尾
$PY main.py pm park   --mission-id <MISSION> --reason x --summary y  # exit 1 只有 RUNNING 或 BLOCKED 的 Run 可以搁着（当前 VERIFYING）
```

D2（P1 坏项目毒化登记）：
```bash
$PY main.py project create --stack python --id ZZ-2026-904 --name drill_py_fake --dest-dir /tmp/drill-ws/0100_项目   # exit 0
$PY main.py project register SW-2026-991          # exit 1 裸 pydantic_core.ValidationError business_line 'ZZ'
rm -rf /tmp/drill-ws/0100_项目/ZZ-2026-904_drill_py_fake
$PY main.py project register SW-2026-991          # exit 0
```

D3（P1 登记表未提交致 verify 失败）：
```bash
$PY main.py project register SW-2026-991          # 写 workspace_registry.json（未提交）
$PY main.py pm verify --mission-id <MISSION> --lease-wallet
# exit 1 EvidenceCollectionError: Run unstaged dirty path 超出 owned_paths: SYS-2026-001_WorkspaceGovernance/workspace_registry.json
```

D4（P2 验证前提交代码）：
```bash
# run start 之后
git -C /tmp/drill-ws commit -qam "work commit"
$PY main.py pm verify --mission-id <MISSION> --lease-wallet    # exit 1 Run git_head 与受管 worktree 当前 HEAD 不一致
```

D5（P1 cover 卡住无法搁置）：
```bash
$PY main.py pm park --mission-id <MISSION> --reason x --summary y   # VERIFYING → exit 1
$PY main.py continuity run transition --run-id <RUN> --to FAILED --owner <owner> --lease-wallet --idempotency-key k
$PY main.py pm park --mission-id <MISSION> --reason x --summary y   # exit 1 必须恰有 1 个未终结 Run（实际 0 个）
```

D6（P1 新工作区入箱被拒）：
```bash
# 全新沙箱、没有 .auto-pm/continuity.db
$PY main.py pm inbox add --project-id SW-2026-991 ...（参数齐全）   # exit 1 Continuity Store 尚未初始化，拒绝创建收件箱表
$PY main.py continuity work create --work-id W-INIT --pid SW-2026-991 --kind TEST --title init --owner x --scope "0100_项目/SW-2026-991_drill_py_fake2" --idempotency-key k0 --read-only
$PY main.py pm inbox add ...                                        # exit 0
```

D7（P2 入箱必填项未标注）：
```bash
$PY main.py pm inbox add ...（缺 --evidence）  # exit 1 pydantic: needs at least one unique evidence entry
$PY main.py pm inbox add ...（补 evidence、缺 --alternative） # exit 1 pydantic: needs at least one alternative
```

D8（P2 续租版本号不可发现）：
```bash
$PY main.py continuity lease renew --run-id <RUN> --owner <owner> --lease-wallet --lease-seconds 3600 --expected-version 3 --idempotency-key k  # exit 1 lease version 冲突
# 依次试 2 → 冲突；试 1 → exit 0
```

D9（P2 回收提示时长不准）：
```bash
$PY main.py continuity run reclaim --run-id <RUN> --claimant <new-owner> --reason x   # 过期后 68s：exit 1 REFUSE_LIVE_LEASE“约 68 秒后…再试”
sleep 75 && $PY main.py continuity run reclaim ...                                    # exit 0 ALLOW
```

D10（P2 按入口路径而非 cwd 判断工位）：
```bash
cd /tmp/drill-ws/.auto-pm/worktrees/drill-w1
$PY /tmp/drill-ws/main.py pm orient SW-2026-991 --json   # exit 0（写的是控制根账本）
$PY main.py pm orient SW-2026-991 --json                 # exit 2 managed candidate is execution-only
```

D11（P2 批准需重填七栏）：
```bash
$PY main.py pm approve --project-id SW-2026-991 --request-id REQ-DRILL-001 --plan-hash <hash> --approver user --approval-evidence-ref user-confirmation:x
# exit 1 缺少必填参数: --objective, --acceptance, --scope, --risk, --non-goal, --adapter, --approved-model
# 全部重填后 exit 0
```
