# Flashback（閃回）— 從 SSD 串流跑 gpt-oss-120b

> 在 24GB 記憶體的 MacBook Air（M5）上，用 mmap 把 63GB 的 MoE 模型「借放」在外接 SSD，
> 需要時才把權重閃回記憶體。名字向 Apple 論文〈LLM in a flash〉致敬。

- 建立日期：2026-11-08
- 測試機：MacBook Air，Apple M5，24GB 統一記憶體
- 儲存：Transcend ESD240C 1TB（卷宗「LLM SSD」），目前連線限制在 USB 5Gb/s
- 這顆 SSD 的基準測試（2026-11-08，關閉系統快取）：

| 項目 | 結果 |
|---|---|
| 循序寫入 | 426 MB/s |
| 循序讀取 | 381 MB/s |
| 4K 隨機讀取（QD1） | 4,229 IOPS，平均延遲 236 µs |
| 4K 隨機寫入（QD1） | 1,835 IOPS |

---

## 目標

1. **能不能跑**：在 24GB 的 Mac 上跑起 63GB 的 gpt-oss-120b。
2. **量化瓶頸**：每產生一個 token 實際要從 SSD 讀多少資料？速度卡在硬碟、CPU 還是記憶體？
3. **幫忙決定要不要買新硬碟**：用實測數據推算換成更快的 SSD 能跑多快。

**原則：** 模型只放在外接 SSD，不佔用 MacBook Air 的內建空間。**所有測試都只跑在外接硬碟上的檔案**（不讀內建硬碟上的模型）。

## 資料夾結構

```
/Volumes/LLM SSD/Flashback/
├── README.md          ← 交接入口
├── PLAN.md            ← 本文件
├── RESULTS.md         ← 結果報告、購買建議、給 Mac mini 的交接建議
├── EXPERIMENT_LOG.md  ← 依時間排列的完整過程
├── models/            ← 120b、20b、EAGLE3 草稿頭、Qwen3-Coder（共約 95GB，不在 git 裡）
├── scripts/           ← 伺服器、量測、排程、熱保護
├── prompts/           ← 測試提示詞（代理多輪、改寫檔案等）
└── logs/              ← llama.cpp、iostat、vm_stat、資源紀錄的原始檔
```

---

## 階段 0：準備

- [x] 用 Homebrew 安裝 llama.cpp（2026-11-08，版本 0.9.0 / build 12110）
- [x] 在背景下載 `gpt-oss-120b-MXFP4.gguf`（63.39GB）— 2026-11-08 01:29–01:47 完成（約 18 分鐘，HF 快取設在 SSD 上的 `.hf_home/`）
  - 來源：Hugging Face `ggml-org/gpt-oss-120b-GGUF`（llama.cpp 官方組織）
  - 存到：`/Volumes/LLM SSD/Flashback/models/`
- [x] 下載完成後核對雜湊值，確認檔案完整 — **吻合**（`logs/sha256.log`；讀完整檔 151.5 秒 ≈ 418 MB/s 循序讀取）（官方 SHA256：`582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d`，大小 63,387,346,208 bytes）
- [ ] （選擇性，由使用者執行）停用這個卷宗的 Spotlight 索引，避免背景索引干擾 I/O 測量

## 階段 1：對照組

- [x] 第 6 項改用外接 SSD 上的 gpt-oss-20b 補做對照（2026-11-08 晚上）：全部放 GPU 46.4 tok/s，見 RESULTS.md
- [~] ~~用 Ollama 跑 gpt-oss:20b~~ — **跳過**（2026-11-08，使用者決定）：Ollama 的模型存放在內建硬碟，違反「所有測試只跑在外接硬碟」原則。已跑到一半的紀錄移到 `logs/invalid_internal_disk/`，不採用
- 這代表「不受硬碟影響」時這台機器的速度上限

## 試跑紀錄（2026-11-08，32 token × 3 提示詞，`logs/trial32_*`）

- 啟動踩坑：llama.cpp 啟動時會對整個檔案做 MADV_WILLNEED 預讀（約 2 分 40 秒讀 64.8GB），無法關閉；只進可丟棄的檔案快取，不會 swap。→ **冷啟動改為「伺服器載入完成後由使用者執行 `sudo purge`」**
- 啟動腳本加上 `--no-repack`（預防專家層被 repack 到一般記憶體）
- 記憶體配置：GPU 1.6GB 共用層 + 0.17GB KV + 0.6GB 計算暫存；專家層 58.8GB 為 CPU_Mapped（mmap）。全程 swapouts = 0
- 生成：0.29–0.43 token/s；每 token 從 SSD 讀 **約 400–600 MB**（理論上限約 1.8GB/token，快取擋掉約 2/3–3/4）
- 讀取型態：**平均每次只讀約 23 KB、約 8,000 次/秒、只跑到 185 MB/s**（循序讀取可達 418 MB/s）→ 瓶頸是小塊隨機讀取的 IOPS／延遲，不是頻寬
- 提示詞處理：約 120 token 要 3 分鐘左右、讀 40–49GB（幾乎把全部專家掃一遍），0.5–0.7 token/s

## 優化調查（2026-11-08，網路資料）

| 來源 | 做法 | 結果（[實測]／[推估]／[宣稱]） |
|---|---|---|
| [Expert Sniper](https://huggingface.co/waltgrace/llama-cpp-expert-sniper)（llama.cpp 補丁） | 路由器選出專家後，對那幾個專家的記憶體範圍呼叫 `madvise(MADV_WILLNEED)`，讓系統一次大塊預讀，不再一頁一頁 page fault | M2 Air 8GB：0.46 → 0.57 tok/s（+24%）[實測]；自製 LRU 快取反而只有 0.24 |
| [llama.cpp 討論 #27149](https://github.com/ggml-org/llama.cpp/discussions/27149) | 只讀被選中的專家、整塊連續讀、讀取與計算重疊 | M1 內建 NVMe 整層連續讀 2.97 GB/s，雙緩衝 6.06 GB/s [實測]；4.7 tok/s 為模擬計算 [推估] |
| [Flash-MoE](https://starlog.is/articles/llm-engineering/danveloper-flash-moe) | 397B 模型在 48GB MacBook 上串流專家；**信任系統 page cache** | 4.4 tok/s、快取命中 71% [宣稱，二手文章]；自製快取方案都比系統快取差 |
| [moe-cache](https://github.com/IbrahimSiddiqui007/moe-cache)（僅 Windows/Linux） | 把實際用到的專家留在 RAM | 提示詞處理 2.2–4.2 倍、生成 +20–36% [實測，GPU 機器] |
| [llama.cpp issue #19825](https://github.com/ggml-org/llama.cpp/issues/19825) | 24GB M4 Pro 超出 RAM 時 swap 爆掉 | `--n-cpu-moe`、`-ngl 0`、調高 `iogpu.wired_limit_mb` 都沒解決 |

**共識：**
1. **不要**用 `--no-mmap`、`--mlock`、CPU repack（Expert Sniper 實測 CPU_REPACK 讓記憶體需求加倍）——本專案已避開
2. **相信系統快取**：多個專案的自製 LRU 都輸給 OS page cache
3. **最大的槓桿是把零碎 page fault 變成大塊讀取**（對應我們試跑看到的 23KB/次、只跑到 185 MB/s）
4. 提示詞處理每個 ubatch（預設 512 token）約掃一次全部專家，所以提示詞越長，每 token 平均成本越低

**對本專案的意義：** 若能改成大塊讀取，這顆 SSD 理論上可從 185 MB/s 提升到約 418 MB/s，生成速度上限約翻倍（約 0.7–1 tok/s，[推估]）。而且讀取型態會決定購買建議看「4K IOPS」還是「頻寬」。

## 階段 2：主實驗

**設定：**
- 注意力層和共用層放在記憶體，由 GPU（Metal）計算
- 專家層透過 mmap 留在 SSD 上：`-ot "exps=CPU"`
- 上下文長度 4096，以節省記憶體

**測試內容（2026-11-08 改為代理負載）：** 真正用途是讓 Claude 透過 opencode 呼叫本地模型寫程式，所以改成模擬寫程式代理的多輪對話（`scripts/agent_bench.py`）：

| 輪次 | 提示詞 | 說明 |
|---|---|---|
| t1_long | `prompts/agent_turn1.txt`，約 2,945 token | 系統規則 + 工具定義 + 讀檔結果（bench.py 全文）+ 任務 |
| t2_followup | 追加 `agent_turn2_add.txt`，約 206 token | 工具輸出（編輯成功 + 測試失敗），前綴快取只需處理新增部分 |
| t3_followup | 追加 `agent_turn3_add.txt`，約 323 token | 工具輸出（traceback） |

每輪產生 64 token。原本的短問答（`prompts/qa_zh.txt` 等）只保留試跑結果作為參考。

**設定組合：**
- [x] A：`-ub 512`（預設）（**兩次都因熱保護中止，無數據**：02:32 第一次、04:30 A' 第 1 輪第 18 分鐘），`sudo purge` 後跑 t1 → t2 → t3（t1 為冷啟動）
  - 2026-11-08 02:29 開始（使用者已 purge）。之後 B、C 由 `scripts/run_overnight.sh` 自動接續（使用者睡覺期間，各段之間冷卻 15 分鐘、伺服器啟動後冷卻 5 分鐘，`caffeinate -i` 防止睡眠，swapouts 超過 1GB 自動中止，紀錄在 `logs/overnight.log`）
  - **02:32 熱保護跳脫**：A 開始 3.5 分鐘熱壓力就到 1（機器從 01:50 起沒休息），A 中止（紀錄移到 `logs/aborted/`，不採用）
  - 使用者指示：**不過熱優先於實驗成功**。改為排程 v3：B → A'（-ub 512，改用 evict 近似冷啟動）→ C；每段前冷卻 20 分鐘且熱壓力須為 0、每輪 t1/t2/t3 之間休息 5 分鐘、熱壓力 ≥1 立即 SIGKILL（`scripts/thermal_guard.sh`），累計跳脫 3 次全部停止
  - B、C 無法 purge，冷啟動改用讀取 24GB 的 `scratch/evict.bin` 擠出快取來近似
  - 預設執行緒數實測為 4（只用效能核心），所以 C 改成比較 `-t 8` 與 `-t 2`
- [x] B：`-ub 2048`（03:11 完成：t1 9.4 分、t2 5.3 分、t3 6.1 分，0.36–0.43 tok/s），重啟伺服器、`sudo purge` 後跑 t1 → t2 → t3，看長提示詞處理是否因掃描次數減少而變快
- [x] C：執行緒變化（-t 8 與 4 相同；-t 2 生成減半到 0.20–0.24 tok/s。07:11 全部完成）（`-t 8`、`-t 2`，與預設 4 比較；ubatch 用 A/B 中長提示詞較快者）

**同時記錄：**

| 指標 | 量測工具 |
|---|---|
| 生成速度（token/s）、提示詞處理速度 | llama.cpp 內建統計 |
| SSD 讀取量與速度 | `iostat`（disk4） |
| 記憶體換頁量 | `vm_stat` 的 pageins 前後差值 |
| 記憶體壓力、swap 用量 | `memory_pressure`、`vm_stat` |
| CPU 使用率 | `top` |


## 階段 3：推算換硬碟的效果

- [x] 完成（2026-11-08），見 RESULTS.md：生成每 token 讀約 580 MB、約 24KB 隨機讀取，硬碟佔 96% 時間

從階段 2 的數據算出：

- **每個 token 平均從 SSD 讀取的 MB 數**（快取未命中的部分）
- **硬碟讀取時間佔每個 token 總時間的比例**

再推算不同硬碟的預期速度：

| 硬碟 | 實際讀取速度 |
|---|---|
| 現在的 ESD240C（5Gb/s，內部為 SATA） | 約 0.4 GB/s |
| USB 10Gb/s 的 NVMe 外接盒 | 約 0.9 GB/s |
| USB4 / Thunderbolt 的 NVMe 外接盒 | 約 3–3.8 GB/s |

**同時觀察讀取型態：**
- 每個專家的權重在檔案中連續存放，預期偏向大塊連續讀取，這時看的是**頻寬**
- 如果實測是零碎的隨機讀取，選購硬碟要改看 **4K 隨機讀取效能**

## 階段 4：購買決策

- [x] 完成，見 RESULTS.md：USB4 推算 1.5–2.5 tok/s，未達 3 tok/s 門檻，不建議為此買硬碟；先在 Mac mini 內建 SSD 試

| 結果 | 結論 |
|---|---|
| 硬碟讀取佔總時間的大部分，且推算 USB4 硬碟能達到每秒 3 個 token 以上 | **值得買**：USB4 NVMe 外接盒，加上 PCIe 4.0、有 DRAM 的 TLC SSD |
| 硬碟讀取佔比不高，瓶頸在 CPU 或記憶體 | **不值得買**，換硬碟幫助有限 |
| 介於兩者之間 | 再評估，或考慮把同一套方法搬到記憶體較大的 Mac mini 上 |

---

## 延伸研究（2026-11-08～09）

使用者決定先在 Air 上把研究做完整，再交接給 Mac mini。結果摘要見 RESULTS.md，過程見 EXPERIMENT_LOG.md。

- [x] 1. 硬碟隨機讀取延遲（`scripts/randread.py`）：同時 2～4 個讀取就到頂；24KB 146 MB/s，1MB 390 MB/s
- [~] 2. 加大 ubatch 和 16k 上下文（`scripts/run_ubatch.sh`）：`-ub 8192` 讀長提示詞快 3.8 倍。白天兩次熱跳脫，4096、2048 沒有數據
- [x] 3. 推測解碼（`scripts/run_spec.sh`）：ngram-mod 1.24×、ngram-simple 1.20×、EAGLE3 0.73×、20b 草稿 0.24×
- [x] 4. 專家層固定在 GPU（`scripts/run_more.sh`）：固定 2 層持平、4 層慢 24%，不建議
- [ ] 5. 模擬代理迴圈：Air 上沒有安裝 opencode，留到 Mac mini 上直接用 opencode 測
- [x] 6. gpt-oss-20b 在同一顆 SSD 上的基準（`scripts/run_20b.sh`）：GPU 46.4、`exps=CPU` 22.6、GPU 加 ngram-mod 119.7 tok/s
- [x] 7. Qwen3-Coder-30B-A3B 速度和品質（`scripts/run_qwen.sh`、`scripts/quality_bench.py`）：`exps=CPU` 1.75 tok/s，加 ngram 2.93；品質 6/6，20b 也是 6/6

**散熱條件：** 11-08 白天沒有風扇時，熱保護跳脫 4 次。15:17 之後 Air 和 SSD 放在空氣清淨機出風口上，之後全程熱壓力 0。

## 下一步：Mac mini（M6、32GB，內建 SSD）

先跑 `scripts/run_mini.sh --dry-run` 檢查環境，再放背景跑 `scripts/run_mini.sh`。腳本會依序做下面的第 0～4 階段；缺少依賴的階段會跳過並把原因寫進 `logs/mini.log`，不會自己下載或安裝。有跳過、載入失敗或量測失敗時，結尾會列出問題，不會寫「全部完成」。

這台 mini 是共用的：開始前 `ollama ps` 必須是空的，也不能有其他重負載（CPU ≥100% 或記憶體 ≥4GB 的程序）。每組開始前會再確認一次，最多等 30 分鐘。短暫的系統程序擋住時，可以用 `ALLOW_BUSY=1` 忽略一般重負載，但不會忽略 Ollama 已載入的模型。

**第 0 階段，Ollama 對照：** Air 上的 29 vs 46 tok/s 模型檔、提示詞和散熱都不同，要在 mini 上重新比。三組都用同樣的提示詞、96 token、`num_ctx` 8192：Ollama 的 `gpt-oss:latest`（`/api/chat`）、llama-server 跑專案的 20b、llama-server 直接載入 Ollama 的 blob。第 1 組對第 3 組看引擎差距，第 2 組對第 3 組看模型檔差距；blob 載不起來時（架構名稱可能不相容）會記錄原因，這時第 1、2 組的差距就同時包含引擎和模型檔。Ollama 的 `num_batch` 是預設值，和 llama-server 的 2048 不同，會影響提示詞處理時間，比較時要記得。不要 `ollama rm gpt-oss:latest`，不要改 `OLLAMA_MODELS`，Codex總攬 在用。

1. 複製 `models/`、`scripts/`、`prompts/`，用 `shasum -a 256` 核對雜湊。`run_mini.sh` 會自己算出專案路徑，不用改 `ROOT`；單獨跑其他腳本時要設 `FLASHBACK_ROOT`。
2. **Qwen3-Coder-30B-A3B（llama.cpp）：** 先試 `EXPS=GPU`，不行再改 `exps=CPU`。跑 `spec_bench`、`agent_bench`（`--fmt chatml`）和 `quality_bench`，和 Air 的數字比較。
3. **Qwen3-Coder-30B-A3B（MLX）：** 同一個模型的 MLX 版，和第 2 步比生成速度、首個 token 時間和長提示處理時間。M6 的 GPU 每核都有 Neural Accelerator，主要看提示處理能不能變快。mlx-lm 0.32.2 只有 `--draft-model` 草稿模型推測解碼，沒有 ngram-mod，比較時要記下這個差別。需要裝在專案內的 mlx-lm（`python3 -m venv .venv-mlx && .venv-mlx/bin/pip install mlx-lm`）和 `models/mlx/Qwen3-Coder-30B-A3B-4bit/`（下載前先確認）。
4. **opencode 實測（第 5 項）：** 三組：Qwen、Qwen 加 `--spec-type ngram-mod`、20b。`tasks/` 的四題每題跑 3 次（`OPENCODE_REPEATS` 可改），記錄通過率、次數間的差異、每輪等待時間和工具呼叫。ngram-mod 這組看的是實際代理任務有沒有幫助，RESULTS 的 1.24×、2.6× 都來自照抄輸入的改寫題。Qwen 的放法跟著第 1 階段：那裡已經退回 `exps=CPU` 就直接用 CPU，否則先試 GPU，`ctx 32768` 放不下再退回 CPU。每題上限 30 分鐘，12 次全部用滿的最壞情況是一組 6 小時。安裝：`npm install --prefix .tools/opencode opencode-ai@1.19.5`。這版只收 V1 設定（`provider`、`permission`），官方文件寫的 V2 格式（`providers`、`permissions`）會被拒絕。換版本要先確認 `scripts/opencode_tasks.py` 的 `write_config`。題目用 `python3 -I scripts/opencode_tasks.py --validate` 驗證。工具已在 Air 上用 20b 驗證過（過程見 EXPERIMENT_LOG.md 2026-11-09）：真的工具呼叫正常，`stream_bench` 和伺服器數字對得上。Air 那次 invoice_rounding 的 FAIL 是舊題目文字造成的，不要和 mini 的結果直接比。
5. **第 4 階段，120b：** `models/` 必須放在內建 SSD，腳本在 mini 上預設量 `disk0`，放別處要自己設 `DISK`。內建硬碟上也有系統和其他帳號的讀寫，MB/token 可能略為偏高。先跑 `randread.py` 量這台硬碟的隨機讀取（約 6 分鐘），和 Air 的紀錄比，才能把 tok/s 的提升拆成硬碟和快取各佔多少：每個 token 讀多少 MB 主要反映快取，同樣的讀取量能多快讀完反映硬碟。接著用 `-c 16384 -b 8192 -ub 8192` 跑 `agent_bench`（`agent_long.txt`），有無 `--spec-type ngram-mod` 各一組，記錄 `ssd_MB_per_gen_token`（生成階段每個 token 讀多少 MB）。這組決定 120b 這條路要不要收掉：每輪等待能不能壓到 1～2 分鐘以內。同時驗證多 8GB 快取的效果：Air 是每個 token 約 580 MB，外推 mini 約 200～320 MB，尚未驗證。
6. **（選擇性）補第 2 項：** `-ub 4096`、`-ub 2048` 在 16k 上下文的數據。

Core AI 目前沒有 opencode 能接的伺服器，先不列入測試。

## 風險與注意事項

- **主實驗時記憶體壓力會很高**：跑之前先關掉 Chrome 等吃記憶體的程式，隨時可以中止。
- **不修改任何系統設定**，包括 GPU 可用記憶體上限（`iogpu.wired_limit_mb`）。
- **跑的時候不要拔 SSD**：mmap 讀不到頁面時，程式會因為 SIGBUS 崩潰。不會損壞資料，但那一輪要重跑。
- **冷啟動量測**：最準的方式是先執行 `sudo purge`（需要使用者自己執行）。若不執行，就改用「重開 llama.cpp，加上讀別的大檔案擠掉快取」的方式來近似。

## 時間與產出

| 項目 | 原本預估 | 實際 |
|---|---|---|
| 下載 | 20 分鐘到 1.5 小時（視網速而定） | 120b 約 18 分鐘；另外三個模型約 10 分鐘 |
| 測試 | 30 到 60 分鐘 | 主實驗一個通宵；延伸研究約一天，主要時間花在每組 20 分鐘的冷卻 |
| 產出 | `RESULTS.md`：實測數據、瓶頸分析、硬碟購買建議 | 另有 EXPERIMENT_LOG.md 和給 Mac mini 的交接建議 |
