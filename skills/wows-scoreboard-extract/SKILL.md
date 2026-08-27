---
name: wows-scoreboard-extract
description: 从《战舰世界》（World of Warships）“我的团队”/赛后战绩截图提取表格信息：玩家、罗马数字船等级、中文船名、击杀数、经验值。用户给 WoWS 战绩截图、要求提取船等级/船名/击杀/经验时使用。依赖 vision-tools 的 glance 做 OCR。
metadata:
  version: 1.0.0
---

# WoWS 团队战绩截图提取

把“我的团队”样式的《战舰世界》赛后战绩表提取为结构化 Markdown 表格。

## 适用场景

- 截图里有“我的团队”表头，下面是一行一行的玩家战绩。
- 用户要求提取：罗马数字等级、船名、击杀数、经验值（玩家名可选）。
- 也适用于带“对手团队”等同类表格；列含义请按实际表头确认。

## 依赖

- `vision-tools` 技能：使用其中的 `glance` 做 OCR / 视觉提问。
- `Pillow` + `numpy`：`scripts/segment_rows.py` 切行使用（可用 `python -m pip install pillow numpy` 安装）。

## 运行方式

### 1. 整图 OCR

先做一次整图 OCR，得到大致表格内容。Windows 下建议显式设置 UTF-8 输出，避免中文变成方块：

```bash
PYTHONIOENCODING=utf-8 "C:\Users\maohaofeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "C:\Users\maohaofeng\AppData\Local\agent-vision-toolkit\bin\glance" "图片路径" --ocr > /tmp/wows_ocr.txt 2>&1
cat /tmp/wows_ocr.txt
```

如果控制台仍乱码，就把输出重定向到 UTF-8 文件后再查看。

### 2. 按行切图复核

当整图 OCR 对中文船名、数字列不清晰时，用脚本把表格切成 7 个数据行：

```bash
python "C:\Users\maohaofeng\.codex\skills\wows-scoreboard-extract\scripts\segment_rows.py" "图片路径" -o rows --scale 3
```

输出 `rows/row_01.png` ～ `rows/row_07.png`。再对每个行图跑 `glance --ocr`：

```bash
PYTHONIOENCODING=utf-8 "C:\Users\maohaofeng\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "C:\Users\maohaofeng\AppData\Local\agent-vision-toolkit\bin\glance" "rows/row_01.png" --ocr
```

如果某行仍不确定，可用 `glance --region` 或对裁剪后的行图做 `-q "请逐字读出这一行的船名和数字"`。

### 3. 列含义与格式

- **等级**：罗马数字，如 `IX`、`VIII`。
- **船名**：中文，可能被截图截断为 `鲁普雷希特...`、`符拉迪沃斯...` 等；尽量补全为完整船名。
- **击杀数**：右侧第一列数字；该列空白表示 0。
- **经验值**：最右列数字。原图常把千位写成空格，如 `1 617` 表示 `1617`，不要把 `1` 当成单独一列。

### 4. 输出格式

统一输出为 Markdown 表格：

```markdown
| 玩家 | 等级 | 船名 | 击杀 | 经验 |
|---|---|---|---|---|
| [NAVI] Neverm... | IX | 鲁普雷希特 | 10 | 1617 |
| ... | ... | ... | ... | ... |
```

最后两行若击杀列为空，写 `0`，可注明“原图击杀列为空”。

## 已知问题

- OCR 偶尔会把 `w` 读成 `kw`、`muhamad` 读成 `muhammad`、`fulanduoo` 读成 `tulanduoo`；玩家名不是重点时可以容忍，精确核对时应放大行图再问 `glance`。
- 如果截图分辨率/字体和这个用例差异较大，`segment_rows.py` 可能切不准；此时退回 `glance --region` 手动框选行。
- 若截图不是“我的团队”表头，改用通用 `vision-tools` OCR，不要套用本技能的固定 7 行假设。
