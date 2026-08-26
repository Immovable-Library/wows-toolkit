# NGA 发帖说明（已脱敏）

NGA 用 BBCode（NGA 代码），不认 Markdown，也不认裸 HTML。发帖请直接复制 `nga_txt/` 里的 `.txt`（BBCode 版），顺序如下：

1 主帖：01_主帖_玩家版.txt
2 楼：02_精英版_公式与可复现.txt
3 楼：03_经验池与舰种系数_独立报告.txt
4 楼：04_剧情地图_行动名映射核验.txt
5 楼（可选）：05_附录_敌军阵容对照.txt（较长可拆两楼）

## html/ 用途

`html/` 内是浏览器预览版（含排版样式），只用于本地预览或发人审阅。不要直接贴 NGA（NGA 会过滤 HTML）。

## 红线：以下含真实账号信息，勿发、勿外传

- ops_efficiency*.jsonl / replays_parsed.jsonl / replays.db（原始回放数据，含账号 ID/昵称/逐人战绩）
- reports/SKmon_*.md（好友账号）
- docs/WOWS_OPERATIONS_DEV_PLAN.md、WOWS_OPERATIONS_STATS_PLAN.md、WOWS_OPERATIONS_SAMPLE_COLLECTOR.md、WOWS_WG_API_REFERENCE.md、vortex_api_postman_reference.md（含真实账号 ID 与昵称）
- skills/wows-replay-parser/SKILL.md（含昵称与本地路径）
- scripts/verify_pr_formula.py（硬编码 account-id）
- crates/wows-toolkit/src/data/wargaming.rs（测试夹具含账号）
- replays/（回放文件名含舰船/分身信息）

## 已脱敏

- 发布版已确认：不含账号 ID（实际值）、昵称、IP、Windows 用户名、真实本地路径。
- 05 中 10 位「未识别船 id」已替换为「未识别单位」，避免被误读为账号 ID。
- BBCode 版已把正文里的方括号转成全角（［］），避免被当成 BBCode 标签。

## 口径

- 经验均为「基础经验」（不含高账 1.65x、首胜）。
- 旗舰为限时模式，已单列、不计入常态。
- 场景中文名以 04 号为准（杀人鲸 / 防守纽波特 / 营救猛禽 / 那莱 / 最终前线 / 赫尔墨斯 / 神盾 / 樱花绽放）。
