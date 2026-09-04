# 剧情敌人显示名与波次命名机制

结论：所有剧情图都使用「固定呼号」来命名敌方单位，名字由 **波次/编组前缀 + 组内序号** 构成。
但不是所有图都用字母表（A/B/C/D/E/F/G）标波次。字母表只是其中两类图的写法。

## 一、字母表类：字头 = 波次/编组

### 北极护航（Arctic Convoy，内部 OP_12）—— 德语音标字母

| 字头 | 显示名 | 内码 | 含义 |
|---|---|---|---|
| A | Anton 1~4 | `IDS_OP_12_ENEMY_WAVE_011~014` | 第一波 |
| B | Bruno 1~4 | `IDS_OP_12_ENEMY_WAVE_021~024` | 一波 |
| C | Cäsar 1~7 | `IDS_OP_12_ENEMY_WAVE_11~17` | 一波 |
| D | David 1~7 | `IDS_OP_12_ENEMY_WAVE_21~27` | 一波 |
| E | Emil 1~12 | `IDS_OP_12_ENEMY_WAVE_ADD_1~12` | 增援 |
| F | Fritz 1~6 | `IDS_OP_12_ENEMY_BOSS_DD_01~06` | BOSS 驱逐（Z-38） |
| G | Gustav 1~10 | `IDS_OP_12_ENEMY_WAVE_31~39` + `_310` | 末波（尾 BOSS 约克 = Gustav 10） |

德语拼读字母表顺序即 A,B,C,D,E,F,G = Anton,Bruno,Cäsar,David,Emil,Fritz,Gustav。
内码后缀（011/021/11/21/ADD/BOSS_DD/31）被刻意打乱，显示名字头才是真正的波次分组。

### 最终前线（The Ultimate Frontier，内部 OP_02_02）—— 北约音标字母

Alpha, Bravo, Charlie, Delta, Romeo, Victor, Foxtrot, Golf, Zulu, Kilo, Lima, Mike, Oscar, Whiskey。
这是 NATO phonetic alphabet（A/B/C/D/F/G/K/L/M/O/R/V/W/Z）。

### 那莱（Narai，内部 OP_02_03）—— 部分北约音标字母

US 组混用 Alpha, Bravo, Foxtrot, Quebec, Tango, Uniform；其余是国别主题名（法国/英国/苏联/防御单位）。

## 二、日式假名风固定名：名字 = 波次，但无字母顺序

这些图的敌人名是短音节（だ/ふ/が/か/ま 等开头的假名风名字），按波次固定，但不按 A-Z 排。

| 地图 | 各波名字族 |
|---|---|
| 神盾（Ridge） | 1 波 Daki/Dako/Dami/Dani/Dano；2 波 Fuda/Fugi/Fugo/Fugu/Fujo；3 波 Gaku/Gama/Gari；4 波 Kaba/Kabi/Kabu/Kado；8/9 波 Mato/Mazu/Miba/Migi/Maji/Maki/Mari/Maku |
| 营救猛禽（Labyrinth） | Kado/Kato/Kimo；Gaki/Geko/Goro；Fuwa/Fusa/Fumi/Fugu；Keko/Kiga/Kimi/Kita/Kori/Kumi；Maku/Muri/Mato/Migo/Misu/Mizo/Moku/Miba；Dobi/Demo/Desu/Dono/Dosu/Date |
| 樱花绽放（Cherry Blossom） | Demo/Doba/Dosu/Dako/Koyama/Kama/Kawa/Kibi/Kiji；Fuju/Fujo/Fugi/Fuda/Kusa；Kuro/Kura/Kubo/Kuji/Kuga/Kuda/Kubi/Kote/Koto |
| 东京快车（Tokyo Express） | Doki 1~3；Gimu 1~17（跨多波）；Fujo 1~3；尾 BOSS Oka；增援 Kaji 1~10 |
| 太平洋攻势（Pacific Offensive） | Doki 1~3；Gimu 1~6；Fujo 1~3；Kaji 1~6；Nensho 1~9 + 尾 BOSS Nensho 10；增援 Mato 1~13 |

## 三、德语人名：名字 = 波次/单位

### 杀人鲸（Killer Whale）

主力 Albert/David/Emil/Friedrich/Futa/Ludwig；增援 Richard/Siegfried/Ulrich/Wilhelm/Paul/Otto/Fritz/Heinrich/Karl/Gustav/Heintz/Jacob/Julius；航母 Fury/Dono/Goku/Deky。

### 赫尔墨斯（Hermes）

Arnold/Baldur/Carl/August/Bastian/Friedolf/Alfred/Ferdinand/Cuno/Dagomar/Curt/Delf/Elmar/Felix/Adler/Dirk/Erich/Ditmar/Franz/Birk/Clemens/Hans/Chris/Tian/Ander/Sen。

## 四、混合/国别主题

### 防守纽波特（Defense of Naval Station Newport）

Dami/Bruno/Otto/Gama/Kagi/Teodor/Fury/Gara/Tatakai/Date/Maki/Carl/Kousotsu/Gunkan/Daki/Fugo/Gaku/Kaba/Albert/Falc/Ulrich/Fritz/Kumo/Chancellor。

### 那莱（Narai）

法国 Cuirassier/Commandant/General；英国 Lycaon/Royal；苏联 Ingénieur/Johnny/Uporniy；US Alpha/Bravo/Omega/Foxtrot/Gun/Cherokee/Quebec/Tango/Uniform/Apache/King/Pilot；防御 Alligator/Elephant/Sapper。

## 说明

- 显示名来自游戏 gettext 目录 `bin/<build>/res/texts/<lang>/LC_MESSAGES/global.mo`。
- 剧情 replay 内只存内码标签（如 `IDS_OP_12_ENEMY_BOSS_DD_01`），显示名是客户端本地化结果。
- 「字母表 = 波次」是北极护航与最终前线最明显的写法；其余图用固定主题名同样编码波次，但不是字母顺序。
