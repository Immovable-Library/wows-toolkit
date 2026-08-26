# 剧情地图 × 场景代码 × 敌军阵容 对照表

> 来源：本地回放解包（playersPublicInfo 中 account_id<0 的 bot 单位）。
>
> 注1：本地回放不含「旗舰（Flagships）」子变体；旗舰为限时模式，其子变体已在经验池报告单列。
> 注2：`?` = 船 id 不在玩家船缓存（多为运输船/特殊单位）。
> 注3：数量 xN 为该档位 N 局汇总（N 见各节标题）。

## 总映射

| 中文名 | 场景代码 | 分房档位 | 敌军特征 |
|---|---|---|---|
| 神盾 | `Ridge` | 普通 6-8、中级 7-9、高级 8-11、旗舰 9-10（限时） | 日系 |
| 杀人鲸 | `NavalBase` | 普通 6-8 | 德日混合 |
| 营救猛禽 | `Labyrinth` | 普通 6-8、中级 7-9、高级 8-11、旗舰 9-10（限时） | 日系（含航母） |
| 防守纽波特 | `Naval_Defense` | 普通 6-8、中级 7-9、高级 8-11、旗舰 9-10（限时） | 德日混合 |
| 那莱 | `Advance` | 普通 6-8 | 美/英/法混合 + 列克星敦 + 密苏里 + 5 艘运输船 |
| 最终前线 | `Atoll` | 普通 6-8、中级 7-9、高级 8-11、旗舰 9-10（限时） | 美系 |
| 赫尔墨斯 | `LePVE` | 普通 6-8、中级 7-9、高级 8-11、旗舰 9-10（限时） | 德系（友军为法系） |
| 樱花绽放 | `USS_CL` | 普通 6-8、中级 7-9、高级 8-11、旗舰 9-10（限时） | 日系巡洋/驱逐（夜战，无战列） |

## 逐图敌军阵容

### 神盾（Ridge）`PCVO001_OP_01_01_37_Ridge` — 普通 6-8（20 局）
- 敌军：
  - 战列：Fusō(T6)×34、Ise(T6)×12、Mutsu(T6)×17、Nagato(T7)×43、Amagi(T8)×14
  - 巡洋：Furutaka(T5)×22、Aoba(T6)×79、Gokase(T6)×8、Maya(T7)×8、Myōkō(T7)×146、Omono(T7)×7、Tokachi(T7)×21、Atago(T8)×6、Mogami(T8)×29
  - 驱逐：Akatsuki(T7)×7、Shiratsuyu(T7)×7、Akizuki(T8)×14、Kagerō(T8)×22、Kitakaze(T9)×11
- 友方非玩家：
  - 4291049456(T?)×100、Saipan(T8)×18、Shchors(T7)×20、Fletcher(T9)×20

### 神盾（Ridge）`PCVO001_OP_01_01_37_Ridge_MEDIUM_LVL` — 中级 7-9（14 局）
- 敌军：
  - 战列：Amagi(T8)×43、Kii(T8)×29、Yumihari(T8)×20、Daisen(T9)×1、Musashi(T9)×1
  - 巡洋：Myōkō(T7)×13、Omono(T7)×2、Atago(T8)×46、Mogami(T8)×54、Shimanto(T8)×7、Tone(T8)×8、Azuma(T9)×39、Ibuki(T9)×31、Suzuya(T9)×23、Takahashi(T9)×13、Zaō(T10)×11
  - 驱逐：Shiratsuyu(T7)×1、Kitakaze(T9)×14、Minegumo(T9)×1、Yūgumo(T9)×12、Hayate(T10)×5、Shimakaze(T10)×2
  - ?：4287509776(T?)×21
- 友方非玩家：
  - 4291049456(T?)×70、Saipan(T8)×9、Shchors(T7)×14、Fletcher(T9)×14

### 神盾（Ridge）`PCVO001_OP_01_01_37_Ridge_HIGH_LVL` — 高级 8-11（23 局）
- 敌军：
  - 战列：Adatara(T9)×1、Hizen(T9)×24、Musashi(T9)×20、Bungo(T10)×22、Grosser Kurfürst(T10)×2、Shikishima(T10)×22、Yamato(T10)×44
  - 巡洋：Mogami(T8)×16、Azuma(T9)×49、Chikuma II(T9)×11、Ibuki(T9)×5、Suzuya(T9)×5、Takahashi(T9)×7、Hindenburg(T10)×1、Yodo(T10)×24、Yoshino(T10)×143、Zaō(T10)×75、Clausewitz(T11)×40
  - 驱逐：Kitakaze(T9)×1、Minegumo(T9)×5、Yūgumo(T9)×3、Harugumo(T10)×24、Shimakaze(T10)×6、Yamagiri(T11)×44
  - ?：4287509776(T?)×28
- 友方非玩家：
  - 4291049456(T?)×115、Franklin D. Roosevelt(T10)×18、Shchors(T7)×23、Gearing(T10)×23

### 杀人鲸（NavalBase）`PCVO002_OP_01_02_s01_NavalBase` — 普通 6-8（29 局）
- 敌军：
  - 战列：Bayern(T6)×116、Fusō(T6)×58、Gneisenau(T7)×56、Bismarck(T8)×14
  - 巡洋：Aoba(T6)×29、Nürnberg(T6)×145、Yorck(T7)×27、Admiral Hipper(T8)×14
  - 驱逐：T-22(T5)×29、Ernst Gaede(T6)×58、Fubuki(T6)×29、Leberecht Maass(T7)×27、Z-23(T8)×14
  - ?：4293146608(T?)×145
- 友方非玩家：
  - Benson(T8)×1

### 营救猛禽（Labyrinth）`PCVO003_OP_01_03_s03_Labyrinth` — 普通 6-8（15 局）
- 敌军：
  - 航母：Kaga(T8)×6、Shōkaku(T8)×24
  - 战列：Kongō(T5)×14、Fusō(T6)×16、Mutsu(T6)×2、Nagato(T7)×10、Amagi(T8)×2、Kii(T8)×2
  - 巡洋：Furutaka(T5)×5、Yahagi(T5)×3、Aoba(T6)×67、Gokase(T6)×5、Maya(T7)×1、Myōkō(T7)×37、Omono(T7)×3、Tokachi(T7)×2、Atago(T8)×2、Mogami(T8)×25、Shimanto(T8)×2
  - 驱逐：Fubuki(T6)×30、Hatsuharu(T6)×15、Shiratsuyu(T7)×15、Kagerō(T8)×4
  - ?：3767448848(T?)×8
- 友方非玩家：
  - 3448747280(T?)×15、4293146608(T?)×15、3439605008(T?)×15、4291049456(T?)×15

### 营救猛禽（Labyrinth）`PCVO003_OP_01_03_s03_Labyrinth_MEDIUM_LVL` — 中级 7-9（19 局）
- 敌军：
  - 航母：Kaga(T8)×19、Shinano(T10)×19
  - 战列：Ashitaka(T7)×4、Hyūga(T7)×3、Nagato(T7)×5、Amagi(T8)×4、Kii(T8)×23、Adatara(T9)×3、Daisen(T9)×1、Hizen(T9)×4、Musashi(T9)×2
  - 巡洋：Myōkō(T7)×4、Omono(T7)×3、Atago(T8)×32、Mogami(T8)×29、Shimanto(T8)×25、Tone(T8)×17、Ibuki(T9)×34、Suzuya(T9)×11、Takahashi(T9)×8、Yodo(T10)×6、Zaō(T10)×30
  - 驱逐：Akatsuki(T7)×3、Shiratsuyu(T7)×12、Akizuki(T8)×19、Kagerō(T8)×19、Kitakaze(T9)×34、Minegumo(T9)×8、Yūgumo(T9)×11
  - ?：4287509776(T?)×21、3767448848(T?)×8
- 友方非玩家：
  - 3448747280(T?)×19、4293146608(T?)×19、3439605008(T?)×19、4291049456(T?)×19

### 营救猛禽（Labyrinth）`PCVO003_OP_01_03_s03_Labyrinth_HIGH_LVL` — 高级 8-11（20 局）
- 敌军：
  - 航母：Hakuryū(T10)×24、Shinano(T10)×16
  - 战列：Amagi(T8)×7、Kii(T8)×2、Yumihari(T8)×4、Adatara(T9)×4、Hizen(T9)×20、Izumo(T9)×5、Musashi(T9)×3、Bungo(T10)×5、Shikishima(T10)×5、Yamato(T10)×6、Satsuma(T11)×5
  - 巡洋：Mogami(T8)×4、Shimanto(T8)×1、Azuma(T9)×74、Chikuma II(T9)×4、Ibuki(T9)×14、Suzuya(T9)×5、Takahashi(T9)×10、Yodo(T10)×4、Yoshino(T10)×36、Zaō(T10)×17、Clausewitz(T11)×39
  - 驱逐：Kitakaze(T9)×41、Minegumo(T9)×5、Yūgumo(T9)×10、Harugumo(T10)×23、Hayate(T10)×16、Yamagiri(T11)×4
  - ?：3767448848(T?)×9、4287509776(T?)×49
- 友方非玩家：
  - 3448747280(T?)×20、4293146608(T?)×20、3439605008(T?)×20、4291049456(T?)×20

### 防守纽波特（Naval_Defense）`PCVO004_OP_01_04_s02_Naval_Defense` — 普通 6-8（18 局）
- 敌军：
  - 战列：Kongō(T5)×18、Bayern(T6)×18、Gneisenau(T7)×18、Nagato(T7)×18、Amagi(T8)×1、Musashi(T9)×12、Yamato(T10)×5
  - 巡洋：Kuma(T4)×18、Furutaka(T5)×18、Yahagi(T5)×18、Aoba(T6)×54、Myōkō(T7)×31、Yorck(T7)×18、Admiral Hipper(T8)×18、Mainz(T8)×1、Mogami(T8)×6、Ibuki(T9)×17、Roon(T9)×17
  - 驱逐：Fubuki(T6)×18、Leberecht Maass(T7)×18、Shiratsuyu(T7)×18、Kagerō(T8)×18、Z-23(T8)×36、Kitakaze(T9)×18
- 友方非玩家：
  - 4291049456(T?)×36、4288952304(T?)×18、Vanguard(T8)×1、Montana(T10)×1、Ohio(T10)×1、Alaska(T9)×1、Seattle(T9)×1、Des Moines(T10)×13、Mahan(T7)×3、Benson(T8)×3

### 防守纽波特（Naval_Defense）`PCVO004_OP_01_04_s02_Naval_Defense_MEDIUM_LVL` — 中级 7-9（19 局）
- 敌军：
  - 战列：Nagato(T7)×19、Prinz Heinrich(T7)×2、Scharnhorst '43(T7)×1、Bismarck(T8)×19、Iwami(T9)×19、Pommern(T9)×19、Schlieffen(T10)×16、Yamato(T10)×3
  - 巡洋：Aoba(T6)×19、Myōkō(T7)×19、München(T7)×1、Omono(T7)×19、Yorck(T7)×1、Atago(T8)×19、Mogami(T8)×19、Shimanto(T8)×19、Tone(T8)×5、Azuma(T9)×19、Blücher(T9)×3、Ibuki(T9)×16、Roon(T9)×19、Suzuya(T9)×3、Hindenburg(T10)×35、Zaō(T10)×19
  - 驱逐：Leberecht Maass(T7)×2、Shiratsuyu(T7)×6、Yūdachi(T7)×4、Z-31(T7)×2、Akizuki(T8)×19、Felix Schultz(T9)×19、Kitakaze(T9)×24、Minegumo(T9)×4、Georg Hoffmann(T10)×19、Shimakaze(T10)×19、Z-52(T10)×19、Yamagiri(T11)×19
  - ?：4287509776(T?)×9
- 友方非玩家：
  - 4291049456(T?)×38、4288952304(T?)×19、Des Moines(T10)×16、Mahan(T7)×1、Benson(T8)×1

### 防守纽波特（Naval_Defense）`PCVO004_OP_01_04_s02_Naval_Defense_HIGH_LVL` — 高级 8-11（22 局）
- 敌军：
  - 战列：Amagi(T8)×3、Friedrich der Grosse(T9)×22、Musashi(T9)×19、Prinz Rupprecht(T9)×1、Bungo(T10)×19、Preussen(T10)×22、Yamato(T10)×3、Hannover(T11)×18、Satsuma(T11)×4
  - 巡洋：Yorck(T7)×3、Admiral Hipper(T8)×3、Amalfi(T8)×3、Mogami(T8)×19、Admiral Schröder(T9)×1、Brindisi(T9)×3、Chikuma II(T9)×2、Ibuki(T9)×19、Roon(T9)×6、Suzuya(T9)×19、Ägir(T9)×1、Hindenburg(T10)×23、Venezia(T10)×6、Yodo(T10)×37、Yoshino(T10)×38、Zaō(T10)×39、Clausewitz(T11)×43、Piemonte(T11)×3
  - 驱逐：Felix Schultz(T9)×1、Kitakaze(T9)×3、Minegumo(T9)×5、Yūgumo(T9)×5、Z-44(T9)×2、Elbing(T10)×47、Harugumo(T10)×30、Hayate(T10)×19、Z-52(T10)×19、Yamagiri(T11)×41
  - ?：4287509776(T?)×27
- 友方非玩家：
  - 4291049456(T?)×44、4288952304(T?)×22、Des Moines(T10)×21

### 那莱（Advance）`PCVO008_OP_02_03_s07_Advance` — 普通 6-8（29 局）
- 敌军：
  - 航母：Lexington(T8)×29
  - 战列：Bretagne(T5)×29、New York(T5)×29、New Mexico(T6)×29、Queen Elizabeth(T6)×58、Colorado(T7)×29、Missouri(T9)×29
  - 巡洋：Omaha(T5)×58、Émile Bertin(T5)×29、Dallas(T6)×29、La Galissonnière(T6)×29、Leander(T6)×58、Indianapolis(T7)×29、Anchorage(T8)×29、Chapayev(T8)×29、Cleveland(T8)×29
  - 驱逐：Wakeful(T4)×29、Nicholas(T5)×29、Farragut(T6)×87、Jervis(T7)×29、Mahan(T7)×29
  - ?：4248057104(T?)×58、4288952304(T?)×29、4247008528(T?)×29、4266931472(T?)×29
- 友方非玩家：
  - 4291049456(T?)×116、4293146608(T?)×29

### 最终前线（Atoll）`PCVO009_OP_02_02_s06_Atoll` — 普通 6-8（20 局）
- 敌军：
  - 战列：Wyoming(T4)×20、New York(T5)×20、Arizona(T6)×2、New Mexico(T6)×22、Colorado(T7)×8、Florida(T7)×2、North Carolina(T8)×10、Iowa(T9)×8、Missouri(T9)×8
  - 巡洋：Phoenix(T4)×17、Marblehead(T5)×16、Omaha(T5)×91、Dallas(T6)×46、Pensacola(T6)×38、Atlanta(T7)×22、Helena(T7)×2、Indianapolis(T7)×20、Baltimore(T8)×2、Cleveland(T8)×28、San Diego(T8)×2、Wichita(T8)×16、Seattle(T9)×8
  - 驱逐：Clemson(T4)×15、Nicholas(T5)×29、Farragut(T6)×48、Mahan(T7)×56、Sims(T7)×27、Benson(T8)×10、Kidd(T8)×10
  - ?：3448747280(T?)×20
- 友方非玩家：
  - Aoba(T6)×20

### 最终前线（Atoll）`PCVO009_OP_02_02_s06_Atoll_MEDIUM_LVL` — 中级 7-9（21 局）
- 敌军：
  - 航母：Hornet(T8)×21
  - 战列：Arizona(T6)×21、California(T7)×21、Colorado(T7)×1、Alabama(T8)×14、Massachusetts(T8)×6、North Carolina(T8)×21、Iowa(T9)×4、Minnesota(T9)×16
  - 巡洋：Pensacola(T6)×13、Atlanta(T7)×30、Flint(T7)×27、Helena(T7)×15、Indianapolis(T7)×5、New Orleans(T7)×14、Baltimore(T8)×20、Cleveland(T8)×28、Rochester(T8)×14、San Diego(T8)×26、Wichita(T8)×13、Buffalo(T9)×4、Seattle(T9)×37、Tulsa(T9)×21、Austin(T10)×16、Des Moines(T10)×6、Salem(T10)×4、Worcester(T10)×14
  - 驱逐：Monaghan(T6)×18、Hughes(T7)×17、Mahan(T7)×9、Sims(T7)×36、Benson(T8)×6、Kidd(T8)×32、Osborne(T8)×2、Black(T9)×9、Fletcher(T9)×33、Johnston(T9)×39、Forrest Sherman(T10)×4、Hull(T10)×16、Somers(T10)×5
  - ?：4287509776(T?)×10
- 友方非玩家：
  - Atago(T8)×21

### 最终前线（Atoll）`PCVO009_OP_02_02_s06_Atoll_HIGH_LVL` — 高级 8-11（23 局）
- 敌军：
  - 航母：Franklin D. Roosevelt(T10)×22、Midway(T10)×1
  - 战列：Colorado(T7)×23、North Carolina(T8)×23、Georgia(T9)×15、Iowa(T9)×23、Missouri(T9)×9、Montana(T10)×10、Vermont(T10)×12、Maine(T11)×2
  - 巡洋：Helena(T7)×15、Baltimore(T8)×22、Cleveland(T8)×36、Alaska(T9)×34、Buffalo(T9)×51、Seattle(T9)×34、Tulsa(T9)×9、Vallejo(T9)×13、Austin(T10)×10、Des Moines(T10)×30、Puerto Rico(T10)×12、Salem(T10)×22、Worcester(T10)×38、Annapolis(T11)×13、Jacksonville(T11)×12
  - 驱逐：Mahan(T7)×1、Benson(T8)×27、Kidd(T8)×6、Osborne(T8)×8、Benham(T9)×10、Black(T9)×6、Christopher(T9)×9、Fletcher(T9)×40、Forrest Sherman(T10)×38、Gearing(T10)×26、Hull(T10)×19、Somers(T10)×8、Joshua Humphreys(T11)×54
  - ?：4287509776(T?)×8
- 友方非玩家：
  - Ibuki(T9)×1、Zaō(T10)×22

### 赫尔墨斯（LePVE）`PCVO010_OP_09_s09_LePVE` — 普通 6-8（24 局）
- 敌军：
  - 航母：August von Parseval(T8)×24
  - 战列：Bayern(T6)×42、Prinz Eitel Friedrich(T6)×6、Gneisenau(T7)×24、Scharnhorst(T7)×24、Tirpitz(T8)×24
  - 巡洋：Leipzig(T6)×6、Nürnberg(T6)×41、München(T7)×19、Weimar(T7)×26、Yorck(T7)×41、Admiral Hipper(T8)×18、Prinz Eugen(T8)×18
  - 驱逐：Ernst Gaede(T6)×76、T-61(T6)×10、Leberecht Maass(T7)×71、Z-31(T7)×47、Z-39(T7)×6、Gustav-Julius Maerker(T8)×5、Z-23(T8)×53
- 友方非玩家：
  - Richelieu(T8)×4、Jean Bart(T9)×13、Alsace(T9)×24、Charles Martel(T8)×11、Saint-Louis(T9)×20

### 赫尔墨斯（LePVE）`PCVO010_OP_09_s09_LePVE_MEDIUM_LVL` — 中级 7-9（26 局）
- 敌军：
  - 航母：Graf Zeppelin(T8)×26
  - 战列：Scharnhorst '43(T7)×2、Bismarck(T8)×26、Odin(T8)×26、Tirpitz(T8)×26、Friedrich der Grosse(T9)×26、Pommern(T9)×26
  - 巡洋：Admiral Scheer(T7)×3、Yorck(T7)×3、Admiral Hipper(T8)×26、Mainz(T8)×23、Admiral Schröder(T9)×15、Blücher(T9)×26、Manteuffel(T9)×7、Roon(T9)×45、Ägir(T9)×46
  - 驱逐：Leberecht Maass(T7)×6、Z-31(T7)×8、Gustav-Julius Maerker(T8)×26、Z-23(T8)×28、Z-35(T8)×44、Felix Schultz(T9)×54、Z-44(T9)×26、Z-46(T9)×49、ZF-6(T9)×26、Georg Hoffmann(T10)×16、Z-52(T10)×26
  - ?：4287509776(T?)×36
- 友方非玩家：
  - Richelieu(T8)×5、Gascogne(T8)×1、Jean Bart(T9)×10、Alsace(T9)×26、Saint-Louis(T9)×16、Carnot(T9)×16、Henri IV(T10)×5

### 赫尔墨斯（LePVE）`PCVO010_OP_09_s09_LePVE_HIGH_LVL` — 高级 8-11（20 局）
- 敌军：
  - 航母：Manfred von Richthofen(T10)×3、Max Immelmann(T10)×17
  - 战列：Friedrich der Grosse(T9)×6、Pommern(T9)×19、Mecklenburg(T10)×17、Preussen(T10)×20、Schlieffen(T10)×20、Hannover(T11)×20
  - 巡洋：Brindisi(T9)×6、Manteuffel(T9)×1、Roon(T9)×18、Hildebrand(T10)×30、Hindenburg(T10)×52、Prinz Adalbert(T10)×5、Venezia(T10)×2、Clausewitz(T11)×36
  - 驱逐：Felix Schultz(T9)×30、Z-44(T9)×7、Z-46(T9)×21、Elbing(T10)×76、Georg Hoffmann(T10)×34、Z-42(T10)×4、Z-52(T10)×74
  - ?：4287509776(T?)×39
- 友方非玩家：
  - Jean Bart(T9)×2、Bourgogne(T10)×20、République(T10)×4、Saint-Louis(T9)×16、Henri IV(T10)×18

### 樱花绽放（USS_CL）`PCVO011_OP_10_s10_USS_CL` — 普通 6-8（25 局）
- 敌军：
  - 巡洋：Furutaka(T5)×18、Yahagi(T5)×44、Aoba(T6)×57、Myōkō(T7)×75、Atago(T8)×25、Mogami(T8)×25
  - 驱逐：Fubuki(T6)×25、Hatsuharu(T6)×100、Shiratsuyu(T7)×224、Akizuki(T8)×25、Kagerō(T8)×37
- 友方非玩家：
  - 4291049456(T?)×50、Lexington(T8)×25、Midway(T10)×25、Fletcher(T9)×50

### 樱花绽放（USS_CL）`PCVO011_OP_10_s10_USS_CL_MEDIUM_LVL` — 中级 7-9（23 局）
- 敌军：
  - 战列：Yumihari(T8)×1
  - 巡洋：Myōkō(T7)×43、Omono(T7)×20、Atago(T8)×23、Mogami(T8)×16、Shimanto(T8)×40、Tone(T8)×6、Azuma(T9)×23、Ibuki(T9)×23、Suzuya(T9)×23、Zaō(T10)×23
  - 驱逐：Shiratsuyu(T7)×5、Akizuki(T8)×46、Kagerō(T8)×69、Kitakaze(T9)×108、Minegumo(T9)×19、Yūgumo(T9)×86、Harugumo(T10)×23、Hayate(T10)×16、Shimakaze(T10)×20
  - ?：4287509776(T?)×37
- 友方非玩家：
  - 4291049456(T?)×46、Lexington(T8)×23、Midway(T10)×23、Fletcher(T9)×46

### 樱花绽放（USS_CL）`PCVO011_OP_10_s10_USS_CL_HIGH_LVL` — 高级 8-11（30 局）
- 敌军：
  - 战列：Adatara(T9)×1、Shikishima(T10)×1
  - 巡洋：Atago(T8)×30、Azuma(T9)×55、Chikuma II(T9)×9、Ibuki(T9)×53、Suzuya(T9)×22、Takahashi(T9)×23、Yoshino(T10)×62、Zaō(T10)×28、Clausewitz(T11)×30
  - 驱逐：Kitakaze(T9)×93、Minegumo(T9)×8、Yūgumo(T9)×70、Harugumo(T10)×171、Hayate(T10)×66、Shimakaze(T10)×28、Yamagiri(T11)×73
  - ?：4287509776(T?)×25
- 友方非玩家：
  - 4291049456(T?)×60、Lexington(T8)×30、Midway(T10)×30、Fletcher(T9)×60
