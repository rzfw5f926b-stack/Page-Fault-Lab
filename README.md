# Flashback（閃回）

測試能不能在記憶體不夠的 Mac 上，用 llama.cpp 的 mmap 直接從 SSD 跑 63GB 的 gpt-oss-120b（MoE）。

**最終目的：** 讓 Claude 透過 opencode，用比現在的 gpt-oss-20b（約 29 tok/s）更大的本地模型寫程式。

**實驗機器：** MacBook Air M5，24GB 記憶體，無風扇。模型放在外接 Transcend ESD240C 1TB（USB 5Gb/s）。

**交接對象：** Mac mini，32GB 記憶體，用內建 SSD。

## 從哪裡開始讀

| 順序 | 檔案 | 內容 |
|---|---|---|
| 1 | [RESULTS.md](RESULTS.md) | 結論、瓶頸分析、換硬碟的推估、購買建議 |
| 2 | [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md) | 依時間排列的完整過程：做了什麼、為什麼、結果、遇到的問題 |
| 3 | [PLAN.md](PLAN.md) | 原始計畫，以及各階段的完成狀態 |
| 4 | [網路上的研究/](網路上的研究/) | 網路資料調查，例如 Apple 的論文 |

## 一句話結論（Air 上）

能跑，但生成速度約 0.42 tok/s，每一輪代理對話要等 5～10 分鐘，對即時寫程式來說太慢。瓶頸約 96% 在 SSD 的小塊隨機讀取（每次約 24KB）。細節和後續測試見 RESULTS.md。

## 資料夾

| 路徑 | 內容 | 在 git 裡？ |
|---|---|---|
| `models/` | 模型檔，共約 95GB：gpt-oss-120b、gpt-oss-20b、EAGLE3 草稿頭、Qwen3-Coder-30B-A3B | 否，另外複製 |
| `scripts/` | 啟動伺服器、量測、排程、熱保護等腳本 | 是 |
| `prompts/` | 測試用的提示詞，包含模擬 opencode 的長提示詞 | 是 |
| `logs/` | 所有原始紀錄，見下方說明 | 是 |
| `.hf_home/` | Hugging Face 下載快取，可刪 | 否 |

### scripts/

| 腳本 | 用途 |
|---|---|
| `start_server.sh` | 啟動 llama-server，主設定為 `-ngl 999 -ot "exps=CPU" --no-repack`。可用環境變數 `CTX`、`BATCH`、`EXTRA` 調整 |
| `agent_bench.py` | 模擬 opencode 的多輪對話（長提示詞加上幾輪工具輸出），記錄速度、SSD 讀取量和 swap |
| `spec_bench.py` | 推測解碼測試：要求模型改寫 bench.py，記錄生成速度和草稿接受率 |
| `bench.py` | 最早的量測腳本，對 llama-server 或 Ollama 送短提示詞 |
| `randread.py` | 硬碟隨機讀取測試，比較不同讀取大小和排隊深度的 IOPS 與延遲 |
| `thermal_guard.sh` | 熱保護：熱壓力 >= 1 就立刻停掉伺服器和量測，並留下 `logs/THERMAL_TRIP_*` |
| `resource_log.sh` | 每 10 秒把 CPU、GPU、記憶體、swap、SSD 速度和熱壓力寫進 `logs/resources.csv` |
| `watchdog.sh` | 早期的記憶體看門狗：RSS 或 swap 超過上限就停掉伺服器 |
| `run_overnight.sh`、`run_ubatch.sh`、`run_spec.sh` | 各輪測試的排程，含冷卻和熱保護規則 |
| `download_extra.sh` | 下載額外模型並核對 SHA256 |

### logs/

檔名格式是 `<測試名稱>_<日期>_<時間>`，同一組測試通常有這些檔案：

- `.jsonl`：量測結果
- `_console.log`：量測腳本的輸出
- `_iostat.log`、`_vmstat.log`、`_therm.log`：背景紀錄
- `server_<測試名稱>_*.log`：伺服器日誌

其他檔案：

| 檔案 | 內容 |
|---|---|
| `overnight.log`、`ubatch.log`、`spec.log` | 各輪排程的過程 |
| `resources.csv` | 12:24 之後連續的資源和溫度紀錄 |
| `THERMAL_TRIP_<時分秒>` | 每次熱保護跳脫的時間點 |
| `sha256.log`、`download*.log` | 下載和雜湊驗證 |
| `aborted/` | 中途放棄的測試 |
| `invalid_internal_disk/` | 作廢的對照組：誤用了內建硬碟上的模型 |

## 在 Mac mini 上重現

1. 安裝 llama.cpp：`brew install llama.cpp`。這次測試用的是 0.9.0（b12110）。
2. 把 `models/` 複製到 Mac mini，再用 `shasum -a 256` 和 logs 裡的雜湊比對。
3. 腳本裡的 `ROOT` 寫死為 `/Volumes/LLM SSD/Flashback`，要改成新的路徑。路徑有空格，一律要加引號。
4. 先跑 `scripts/start_server.sh`，再跑 `scripts/agent_bench.py`，就能直接和 Air 的數字比較。

## 實驗守則

- 電腦不過載是最高優先：熱壓力 >= 1 就停，寧願實驗失敗。
- 不修改系統設定，例如 `iogpu.wired_limit_mb` 和 Spotlight。需要 sudo 的指令交給使用者自己執行。
- 下載前先確認；長時間的工作放在背景跑。
