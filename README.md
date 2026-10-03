# GloFAS 历史河流流量下载工具

通过 CEMS Early Warning Data Store（EWDS）下载 GloFAS 历史数据，保存为 NetCDF（`.nc`）。默认下载 **V5.0、consolidated 产品、中国矩形区域、2020—2024 年的逐日河流流量**。

脚本按月请求数据，全年完成后自动合并为一个年度文件。年度文件保留逐日记录，**不是年均值或年总量**。月文件保留，以便恢复和检查。

## 1. 安装依赖

推荐在自己的 Python 或 Conda 环境中执行：

```powershell
python -m pip install -r requirements.txt
```

安装依赖和运行脚本必须使用同一个 Python。若使用本项目最初的 Windows `deepwater` 环境：

```powershell
& "D:\ANACONDA\envs\deepwater\python.exe" -m pip install -r "E:\径流数据\requirements.txt"
```

上面的绝对路径仅为本机示例，其他电脑需要修改为自己的路径。无需安装 LaTeX、GRIB 转换工具或额外插件。

## 2. 配置账号和下载许可

1. 注册或登录 [EWDS](https://ewds.climate.copernicus.eu/)。
2. 在 [GloFAS 历史数据下载页](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=download) 手动接受数据使用条款。
3. 登录 [API 配置页](https://ewds.climate.copernicus.eu/how-to-api)，获取个人访问令牌。
4. 在用户主目录创建 `.cdsapirc`，Windows 通常为 `C:\Users\你的用户名\.cdsapirc`，内容为：

```yaml
url: https://ewds.climate.copernicus.eu/api
key: YOUR_PERSONAL_ACCESS_TOKEN
```

不要保存为 `.cdsapirc.txt`。也可以通过环境变量 `EWDS_API_KEY` 提供令牌。不要将真实令牌写入代码、README 或提交到 GitHub。

## 3. 默认运行

在脚本目录打开终端：

```powershell
python download_glofas.py
```

本机 PowerShell 示例，无需切换工作目录：

```powershell
& "D:\ANACONDA\envs\deepwater\python.exe" "E:\径流数据\download_glofas.py"
```

默认输出到脚本所在目录下的：

```text
glofas_china/v5_discharge_54_73_3_136/
    2020_01.nc
    2020_01.request.json
    ...
    glofas_china_discharge_2020.nc
    ...
    glofas_china_discharge_2024.nc
```

`glofas_china` 是历史命名；修改区域后，文件名仍含 `china`，实际范围以参数目录名和年度文件的 `region_bbox_nwse` 属性为准。

## 4. 可修改项

优先通过命令行传参，无需编辑源代码。参数可组合使用。

| 参数 | 默认值 | 修改方法 |
| --- | --- | --- |
| `--years` | 2020 2021 2022 2023 2024 | 空格分隔，逐个列出年份 |
| `--area` | 54 73 3 136 | 顺序为北、西、南、东，单位为度 |
| `--version` | `version_5_0` | 支持 `version_4_0`、`version_5_0` |
| `--product-type` | `consolidated` | 可选 `intermediate`，需核实所选年份可用性 |
| `--variable` | `discharge` | 可选 `runoff`，说明见下文 |
| `--output` | 脚本目录下的 `glofas_china` | 指定输出根目录，含空格时加引号 |
| `--dry-run` | 不启用 | 只打印首年 1 月请求，不联网下载 |

### 修改年份

```powershell
python download_glofas.py --years 2022 2023 2024
python download_glofas.py --years 2025
```

`--years 2020 2024` 只下载这两个年份，不表示连续范围。连续年份需全部列出。脚本下载所选年份的全部月份，不支持通过参数只选某几个月。

### 修改区域

```powershell
python download_glofas.py --area 34 90 24 123
```

这是修改矩形范围的示例，**不是经过验证的长江流域完整边界**。区域顺序必须为 `[北纬, 西经度, 南纬, 东经度]`，东经、北纬为正，西经、南纬为负；北大于南，东大于西。脚本不支持跨日期变更线的矩形。

默认矩形包含邻国和海域；下载后若需要严格中国区域或长江流域，需要另外用边界文件裁剪。断面分析需结合河道位置和上游汇水面积匹配网格，不能只取最近网格。

### 修改版本和产品

```powershell
python download_glofas.py --version version_5_0
python download_glofas.py --version version_4_0
python download_glofas.py --version version_5_0 --product-type intermediate --years 2025
```

V4 和 V5 输出到不同目录；intermediate 也有独立目录，不会复用 consolidated 文件。consolidated 由正式 ERA5 驱动，intermediate 由初步版 ERA5T 驱动，两者可能存在差异。研究时建议采用一致的版本和产品。

截至 2026-10-02，已核实 V5 consolidated 支持 2020—2024 年全部日期。V4 consolidated 在 2024 年 12 月缺少 31 日。本脚本严格检查日记录，不自动混用产品、不插值填补缺日。`repair_december.py` 是本机旧 V4 数据的一次性修复工具，固定了路径和日期，不是通用下载入口。

### 修改变量

`discharge` 对应 `average_river_discharge_in_the_last_24_hours`，请求 `time_mean`，单位通常为 m³/s，适用于河流水质断面浓度分析。

`runoff` 对应 `runoff_water_equivalent`，表示地表与地下产流之和，不能当作河道流量。当前代码映射到 `instantaneous`；使用前必须在网页的 **Show API request** 中核实所选版本支持的 `timespan`，如官方要求 `time_mean`，修改源代码 `VARIABLES` 中 runoff 元组的第二个值。以下载文件的单位和时间统计定义为准。

```powershell
python download_glofas.py --variable runoff --dry-run
```

### 组合参数

```powershell
python download_glofas.py --years 2023 2024 --version version_5_0 --area 54 73 3 136 --output "E:\GloFAS_data"
```

### 修改永久默认值或增加新版本

若希望省略参数时使用自己的设置，在 `main()` 的 `parser.add_argument` 中修改相应 `default`：年份为 `list(range(开始年份, 结束年份 + 1))`，区域为 `[北, 西, 南, 东]`。版本默认值在文件顶部 `SYSTEM_VERSION` 中设置。

未来新增版本时，在 `--version` 的 `choices` 中加入官方版本标识，并核对数据集页面生成的 API 请求。只改版本字符串不能保证未来接口兼容。`base` 中的 `hydrological_model`、`data_format`、`timespan` 等也须符合官方参数。

不要在已有选择目录中修改变量含义或时间统计方式后继续复用旧缓存。若修改 `VARIABLES`、数据集或其他未反映在目录名中的请求设置，请使用新的 `--output` 目录。

## 5. 时间标记与完整性

河流流量的 `valid_time` 是前 24 小时平均值的结束时间，例如 `2025-01-01 00:00` 对应 2024-12-31 开始的统计区间。脚本保留原始时间，年度文件额外提供 `interval_start`。匹配水质采样时还需统一时区和采样窗口，不要直接把结束时间当成统计日。

每个月和年度合并后均检查每天一条记录，闰年要求 366 条，平年要求 365 条。年度文件包括 `system_version`、区域和逐日 `product_type` 来源信息。日期完整不等于模型精度已验证。

## 6. 续下载与常见问题

- `accepted`、`running`：服务器接受请求并处理数据，保持终端打开。
- `Already complete`：已有年度文件通过日期检查，跳过下载。
- 中断后运行相同命令：完整月文件可复用。零字节 `.download` 自动备份并重新下载；新请求先写入 `.transfer`，下载返回且非空后才作为 `.download` 使用。非空但损坏或不完整的 `.download` 仍可能报错；将该文件重命名备份后重新运行即可重新请求该月。
- `ModuleNotFoundError`：使用运行脚本的同一个 Python 执行 `-m pip install -r requirements.txt`。
- 认证或许可错误：检查 `.cdsapirc` 的 EWDS 地址、令牌以及网页许可是否已接受。
- `invalid request`：核对官方版本、年份、产品和变量组合，使用网页生成的新请求。
- `Missing or duplicate daily records`：检查实际日期与官方可用范围，不要直接取消完整性检查。
- 中文路径：脚本将文件复制到系统临时目录读取，绕过部分 Windows netCDF4 构建的中文路径问题。系统临时目录最好使用 ASCII 路径，并预留空间。

全年合并需要额外临时磁盘空间和内存；大区域可占用数 GB。脚本保留月文件，不会自动删除数据。

## 7. 上传 GitHub

建议提交 `download_glofas.py`、`README.md`、`requirements.txt`、`.gitignore`。无需提交本机一次性修复脚本或下载的数据。

`.gitignore` 排除了凭证、默认数据目录和 NetCDF 文件，但不能保护已经被 Git 跟踪的文件；提交前检查待提交内容。脚本没有自动发布或上传功能。

## 官方参考

- [数据集与许可](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical)
- [EWDS API 配置](https://ewds.climate.copernicus.eu/how-to-api)
- [官方 API 示例](https://confluence.ecmwf.int/spaces/CEMS/pages/242067432/EWDS+API)
- [V5 水文再分析说明](https://global-flood.emergency.copernicus.eu/news/252-the-new-copernicus-glofas-v50-hydrological-reanalysis-has-been-released/)

用于论文时，请遵守数据许可并采用数据集页面的官方引用信息。本仓库代码的许可需由仓库所有者自行决定。
