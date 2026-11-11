# Codex總攬 測試需求 2-3：回歸組 T1～T5 K=3，放寬步數和逾時（Qwen3.6-35B-A3B，llama-server mmap）

2026-11-12 00:02～03:58，Mac mini（M6、32GB）。每次嘗試一行，在同目錄的 `reg_qwen3.6-35b-a3b_night6x.jsonl`（20 行）。原始紀錄在 Codex總攬 的 `exp/accept_results_k3_llama_qwen3.6-35b-a3b_night6x.txt` 和 `exp/llama_logs/` 同名目錄。

目的（測試需求 2-3）：同一組題目，比較「派工目前的條件」和「半夜放寬的條件」，看放寬能救回幾題、會不會多出空轉。

## 和對照組（night5r）的差別

| | night5r（對照） | **night6x（放寬）** |
|---|---|---|
| worker 步數上限 | 20（同派工） | **50**（`OC_STEPS=50`） |
| 每次嘗試逾時 | 3,600 秒 | **7,200 秒**（`OC_TIMEOUT=7200`） |

其他相同：`--cache-ram 0`、整輪不重啟、`RESIDENCY=1`、ctx 65536、`-b/-ub 512`、`exps=CPU`、單一 slot、output 上限 32768、停滯判定 1800 秒、自動重試最多 2 次、`--max-lines` 8。和正式派工條件的其他差異同 `摘要_hard_qwen3.6-35b-a3b_night3.md` 開頭的表。思考額度兩輪都已經是 32768（需求寫的「28k 以上」），這次沒有再放寬。

## 結論：放寬只對 T5 有用，K=3 的總成績沒有變好

| 計法 | night5r | **night6x** |
|---|---|---|
| 單次（含自動重試） | 14/15 | **13/15** |
| pass^3 | 4/5 | **3/5** |
| 第一次就過 | 13/15 | **12/15** |
| T1～T4 第一次就過的平均時間 | 281 秒（11 次） | **301 秒（10 次）** |
| 總耗時 | 3.6 小時 | **3.9 小時** |
| 假完成 | 0 | **1** |

| 題 | r1 | r2 | r3 |
|---|---|---|---|
| T1 | **改動過大 ×3** | ok 196s | 改動過大 ×2 → 第 3 次 ok |
| T2 | ok 472s | ok 382s | ok 340s |
| T3 | ok 250s | ok 193s | ok 232s |
| T4 | ok 187s | ok 548s | ok 211s |
| T5 | ok 253s（6 步） | **假完成（20 步、3,712 秒）→ 重試 header 逾時** | ok 3,285s（**35 步**） |

- **救回 1 次**：T5 r3 用了 35 步、3,285 秒才過。照派工的 20 步，這次會在第 20 步被截斷，算步數用完。
- **放寬反而讓 1 次變成假完成**：T5 r2 第 1 次跑了 3,712 秒，超過原本的 3,600 秒。照原本的條件會是逾時（可以機械判定），放寬後模型多跑了一段，最後說完成但改錯檔案（見下面）。
- **T1 不受影響**：改動過大是 `--max-lines` 擋的（測試都過，diff +12，上限 8），和步數、時間無關。night3r、night5r 的 T1 r1 也一樣。
- T5 三輪過 2 輪，和 night5r 相同。K=3、一輪對照，看不出放寬的淨效果；能確定的是放寬會讓 T5 的失敗型態從「步數用完、逾時」變成「假完成、header 逾時」，後兩種比較難處理。

## 失敗細節

- **T5 r2 第 1 次：假完成。** 模型被 `--deselect` 掉的那個測試（`test_report_benchmark.py::test_real_data_reconciles_and_matches_hand_calc`，要真實資料庫）吸引，花了很多步在它上面，最後在 `report_benchmark.py` 加了「資料庫不存在就回傳空 dict」的 2 行，回報「All 4 tests pass」。它跑的是 `tests/test_report_benchmark.py`，沒有看到 `tests/cio/test_daily.py` 的 2 個失敗（真正的 bug 在 `cio/daily.py`，r1、r3 都是改這裡）。派工的 `--check` 跑完整測試，抓到 2 failed，改動被還原。單一回合最久等了 1,580 秒（約 26 分鐘），output 41,438 token，context 峰值 59,665。這是回歸組第一次出現假完成；被規格測試擋下，不是假通過。
- **T5 r2 第 2 次：header 逾時（執行錯誤）。** server log 顯示主請求生成了 18,894 token（約 20 分鐘，15.7 t/s）後被 opencode 取消；這段時間 opencode 平行送出的另一個請求在單一 slot 後面排隊，每 5 分鐘等不到 header 就重送，最後整個嘗試判成 `provider.transport: Timed out waiting for response headers`。和 night3 H2 r1 同一型。派工不會重試執行錯誤，這輪算失敗。
- **T1 r1、r3**：同上，改動過大。

## 空轉

- 放寬後沒有出現「一直跑卻沒有進展」的空轉：最長的嘗試（T5 r2 第 1 次 3,712 秒、T5 r3 3,285 秒）每一步都有工具呼叫或輸出，停滯判定沒有觸發。
- 但 T5 會用掉很多時間和 context：兩次長嘗試的 context 峰值 59,665 和 54,461（上限 65,536），單一回合思考最多 26 分鐘。這種長思考會碰上上面的 header 逾時，放寬逾時並不能避免。
- 沒有碰到 context 上限（`exceed_context_size_error` 0 次）。

## 速度與資源

`--cache-ram 0` 下速度一樣沒有隨時間掉（`scripts/server_speed_ctx.py`）：開機 60 分鐘後、context <10k，生成 16.1 t/s、讀提示詞 93 t/s；context ≥30k 時生成 11.2 t/s。server log 裡沒有「making room for prompt cache entry」。

熱壓力全程 0。server footprint 2.4～3.7GB。可用記憶體最低 46%。swap 從 4,611MB 開始，開機 30～60 分鐘間最高約 7.8GB（+3.2GB，門檻 +6GB），之後回落，結束時 4,456MB。沒有觸發任何保護。開跑時 `ollama ps` 是空的。

## 轉檔腳本的修正

`oc_llama.py` 設了 `OC_STEPS` 時，`config.json` 的 `steps` 是字串（"50"），`codex_exp_report.py` 拿它和整數比較會出錯。已改成讀進來時轉成整數；night5r 重轉後和原檔逐位元相同。
