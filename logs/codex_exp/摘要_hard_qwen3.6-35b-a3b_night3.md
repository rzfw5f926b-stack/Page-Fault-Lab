# Codex總攬 測試需求：難題組 H1～H6 K=3（Qwen3.6-35B-A3B，llama-server mmap）

2026-11-11 02:15～09:05，Mac mini（M6、32GB）。每次嘗試的細節在同目錄的 `hard_qwen3.6-35b-a3b_night3.jsonl`（19 行，每次嘗試一行）。原始紀錄在 `~/Claude/Codex總攬/exp/accept_results_hard_llama_qwen3.6-35b-a3b_night3.txt` 和 `exp/llama_logs/accept_results_hard_llama_qwen3.6-35b-a3b_night3/`。

這份只涵蓋 **1-1、4，以及 2-1、2-2、3-1 的部分答案**。回歸組（1-2）、2-3、3-2 還沒跑。

## 和 Codex總攬 派工條件不同的地方

照做法 1，用 Codex總攬 的 `exp/accept_hard.sh` 和 `exp/oc_llama.py`（commit 2b558d8）跑，worker 提示、權限、steps 20、`--check`、`--max-lines`、allow 清單、失敗還原、自動重試 2 次，都沿用 `dispatch.py`。不同的地方：

| 項目 | 派工 | 這輪 |
|---|---|---|
| 推論 | Ollama | llama-server（llama.cpp build 12110），`-ot exps=CPU`（專家層走 mmap）、`-b/-ub 512`、`-c 65536`、`--jinja`，Metal residency 開（`RESIDENCY=1`） |
| 模型 | gpt-oss:20b 等 | Qwen3.6-35B-A3B Q4_K_M（ggml-org，20.5GB） |
| output 宣告 | 8192 | 32768（`LLAMA_OUTPUT`，放寬思考） |
| 單次逾時 | 600 秒（難題組） | 3600 秒 |
| 停滯判定 | 120 秒 | 1800 秒，且要 `exec.jsonl` 沒長、`/slots` 也沒變 |
| opencode | 同一支 | v2.1.3；Code Mode 的 `execute` 被 `oc_llama.py` 設為 deny |
| header 逾時 | — | opencode 預設 5 分鐘（`oc_llama.py` 設的 provider `timeout` 7200s 不管 header），見下面的 H2 r1 |
| 每題之間重啟 server | — | 沒有重啟，整晚同一個 server |

## 成績

| 計法 | 結果 |
|---|---|
| Codex總攬 腳本的計法（每輪含自動重試，最後過就算過） | **pass^3 5/6 題、單次 17/18** |
| 每輪第一次嘗試就過（不靠重試） | 16/18（pass@1 = 0.89） |
| pass@3（3 輪內至少一輪過） | 6/6 |
| pass^3（3 輪都過，含重試） | 5/6（H2 2/3） |
| pass^3（3 輪都過，且都是第一次就過） | 4/6（H2、H4 各有一輪沒在第一次過） |

| 題 | r1 | r2 | r3 |
|---|---|---|---|
| H1 多檔多 bug | ok 1225s | ok 1197s | ok 1158s |
| H2 多檔 2 個 bug | **crash**（header 逾時）1218s | ok 2208s | ok 2518s |
| H3 | ok 596s | ok 908s | ok 695s |
| H4 | ok 710s | ok 902s | **wrong（假通過）** 1534s → 重試 ok 1179s |
| H5 新功能 | ok 1546s | ok 1498s | ok 1507s |
| H6 多檔重構 | ok 1089s | ok 1158s | ok 1125s |

### 和 gpt-oss、M3 對照（難題組，同一組腳本）

| 模型 | 難題組 | H2 | H5 | H6 |
|---|---|---|---|---|
| gpt-oss（Ollama） | 7/12（2 輪） | 只修一個或提早放棄 | 改簽名沒改呼叫端，三次都沒做完 | 用完 20 步沒跑測試 |
| MiniMax M3 | 11/12 | — | — | — |
| **Qwen3.6-35B-A3B（llama-server）** | **17/18（3 輪）** | 跑完的兩輪都修到兩個 bug；失敗那輪是傳輸逾時，不是放棄 | 3/3，沒有簽名問題 | 3/3，每次都有跑測試 |

（回歸組的對照：gpt-oss 15/15，這輪還沒跑回歸組。）

## 失敗類型計數（19 次嘗試）

| result | 次數 |
|---|---|
| ok | 17 |
| wrong（規格過、隱藏沒過） | 1（H4 r3 第 1 次） |
| crash（傳輸錯誤） | 1（H2 r1） |
| budget／timeout／stall／ctx_overflow／too_many_lines／touched_other_files | 0 |

## 第 4 部分：假通過、假完成

- **假通過 1 次**：H4 r3 第 1 次。既有測試 364 個都過（check rc=13），隱藏測試 `test_zero_or_missing_target_liquidates` 沒過。模型把 `liquidate=(tgt < REBALANCE_BAND)` 改成別的錯誤條件；自動重試的第 2 次改成 `tgt == 0`，全部通過。
- **假完成 1 次**：就是同一次，模型回報「The fix is in place」。
- 以規格測試通過的 18 次來算，假通過率 1/18。
- 每次說完成的嘗試，都有真的跑過測試（`shell_cmds` 裡有 pytest）：16/16。（2026-11-11 晚更正，原寫 17/17：轉檔腳本改用 `exec.jsonl` 最後一步判斷後，H5 r1、H2 r2 的第 1 次是改動已經通過、但在第 19 步還在呼叫工具時被截斷，模型沒有說完成，改記為步數用完。）
- 沒有留下 allow 以外的檔案，也沒有被 `--max-lines` 擋下；M3 在 H3 留下暫存檔的問題，這裡沒有出現。

## 第 2 部分（部分）

> **2026-11-11 15:30 更正**：下面「單回合思考超過 5 分鐘就一定失敗」是錯的。回歸組 night3r 有一個請求連續生成 21.8 分鐘也沒逾時。重新看 server log，逾時的是和第一個請求幾乎同時送出、排在它後面的第二個請求。詳見 `摘要_reg_qwen3.6-35b-a3b_night3r.md` 的「修正 night3 對 header 逾時的判斷」。
>
> **2026-11-12 再更正**：跑了約 20 分鐘的 task 15334 提示詞只有約 580 token，是每次嘗試開頭 opencode 平行送出的小請求（推測是產生標題），不是主請求；排隊等不到 header 的 15335 才是主請求。詳見 `摘要_reg_qwen3.6-35b-a3b_night6x.md` 的「每次嘗試開頭的小請求」。

- **2-1 思考空轉**：opencode 回報的 reasoning token 一律是 0，思考算在 output 裡，所以 `think_tokens` 分不出來。用 output token 代替：每次嘗試中位數 2,787，最大 12,398（H1 r1）。沒有任何一次用完額度（budget 0 次）。
  - **新發現的失敗模式**：H2 r1 第一回合思考了約 17,400 token（約 18 分鐘，15.7 t/s）。opencode 每 300 秒報一次 `provider.transport: Timed out waiting for response headers` 並重送；單一 slot 讓重送的請求只能排隊，4 次後放棄，判成執行錯誤。
  - opencode 官方文件（https://opencode.ai/docs/providers/ ）寫 header 逾時預設 5 分鐘，要另外設 `headerTimeout`；provider 的 `timeout` 只管整個請求。這是 Haiku 查到的，欄位應該放在 `options` 還是 `settings` 還沒驗證。`oc_llama.py` 沒設，所以單回合思考超過 5 分鐘就一定失敗。這屬於轉接層，Flashback 沒改。
  - 這個失敗可以機械判定：`attempt1.json` 的 `reason=執行錯誤`，`exec.jsonl` 最後一行是 `type:error`。
- **2-2 context**：每次嘗試的峰值（`max_step_input`）中位數 17,038，最大 42,456（H2 r3）。超過 65,536 的情況，在前一輪 night（2026-11-10 22:44）H1 r1 碰到過：llama-server 回 400 `exceed_context_size_error`，opencode 記成錯誤，可以機械判定，沒有靜默截斷。

## 第 3 部分（部分）

- **3-1 連續 6 小時 50 分（19 次嘗試）沒出事**。llama-server 沒掛、沒有殘留程序、熱壓力全程 0、可用記憶體最低 30%。swap 從 5,121MB 到 6,200MB，最高 6,824MB（比開跑時 +1.7GB，門檻 +6GB）；wired 全程 6.9～7.3GB。
  - swap 有 3 次在 1 分鐘內 +1.0～1.2GB（06:18、07:20、08:17），都落在題目交接的時候。
  - 對照：前兩晚用 `GGML_METAL_NO_RESIDENCY=1`（server 閒置時解除 Metal 緩衝區的 wired），都在第 2 題被 swap 暴增中止（一次 7 秒 +8GB），wired 在 3.3GB 和 7.1GB 之間切換。改成 residency 開之後，沒有再發生這種暴增。
  - 還沒做：「每題之間重啟 vs 不重啟」的比較、回歸組混跑、20～30 題。
- **3-2 和其他程式同時跑**：還沒專門測。開跑時 `ollama ps` 是空的；整晚 launchd 排程照常運作，沒有觸發記憶體保護，但沒有逐項記錄當時跑了哪些排程。
