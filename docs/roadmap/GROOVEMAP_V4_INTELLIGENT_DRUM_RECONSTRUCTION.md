# GrooveMap V4 — Intelligent Drum Reconstruction
## Suno / AI Music Drum Restoration & Automatic Sample Matching

> **產品企劃與技術規格｜研發待辦文件**
>
> - Repository：`kevin781130-netizen/GrooveMap`
> - Product line：GrooveMap V4
> - Status：PROPOSED — 尚未進入程式實作
> - GitHub backlog：[#6 GrooveMap V4 研發企劃](https://github.com/kevin781130-netizen/GrooveMap/issues/6)
> - Priority：P1 Product Expansion（須先完成 V3 基底確認）
> - Created：2026-11-27
> - Primary target：Windows 11 + NVIDIA RTX 5090
> - Secondary target：macOS
> - Existing V3 release checklist：[#5 GrooveMap 封版待修清單](https://github.com/kevin781130-netizen/GrooveMap/issues/5)
> - V3 implementation reference：[#4 GrooveMap V3 CLI RC（Draft PR）](https://github.com/kevin781130-netizen/GrooveMap/pull/4)

---

## 1. Executive Summary

GrooveMap V4 的目標，是把 GrooveMap 從鼓組節奏分析與 MIDI 整理工具，擴展為一套專門處理 Suno 及其他 AI 生成歌曲鼓組音質的 **Intelligent Drum Reconstruction（智慧鼓組重建）** 工具。

產品不重新編曲、不重新生成鼓，也不要求使用者手動搜尋 Sample。系統必須先理解原始鼓組的演奏事件與聲學特徵，再從使用者自己的本地 Sample Library 自動找到最接近的高品質素材，最後依照不同鼓件的特性進行疊加或完整替換。

### 核心使用流程

1. 匯入 Suno 完整歌曲，或已分離的 Drum Stem。
2. 自動分離 Kick、Snare、Tom、Hi-Hat、Ride、Crash。
3. 沿用 GrooveMap 的 Beat / Onset / Tempo / Velocity 分析能力，取得原始演奏事件。
4. 對每次擊打分析 Pitch / Resonance、Transient、Timbre、Envelope、Decay。
5. 自動搜尋本地 Sample Library，選出最接近原始聲音的 Sample。
6. Kick / Snare / Tom 使用原音保留＋新 Sample 疊加。
7. Hi-Hat / Cymbals 使用新 Sample 完整替換，保留演奏時間、力度、Articulation 與尾音特徵。
8. 自動完成時間、音高、相位、增益與動態匹配。
9. 輸出重建後的鼓組分軌、MIDI、Tempo Map 及可供 DAW 使用的 WAV。

**產品差異化不是「可以替換鼓聲」，而是「使用者不用找 Sample，系統就能自動找到最接近的聲音並完成替換」。**

---

## 2. Product Principles

### 2.1 必須遵守的設計原則

- **Reuse-first：** 優先沿用 GrooveMap V3、成熟開源分離引擎及既有 DSP 函式庫。
- **Automatic-first：** Sample 搜尋、排序、選擇及替換必須自動完成；人工挑選不得成為主要工作流程的必要步驟。
- **Groove preservation：** 不任意量化、不重新安排節奏、不改寫原始演奏。
- **Drum-specific processing：** 不同鼓件採用不同分析、匹配及重建策略。
- **Local-first：** Sample Library、指紋索引、分析及主要處理流程以本地運行為優先。
- **Deterministic DSP：** 聲學分析、匹配、時間對齊及渲染由可測試的 DSP / 演算法負責；LLM 不負責直接決定 Pitch、相位或 Sample 匹配結果。
- **Auditable output：** 每次重建都保留來源、候選、匹配分數、處理參數及輸出證據。
- **No destructive editing：** 原始音訊不覆寫；所有處理均輸出至新的工作目錄。

### 2.2 明確不做的事情

- 不開發完整 DAW。
- 不重新開發完整 MIDI 編輯器。
- 不自行訓練大型 Drum Separation 模型。
- 不建立新的 AI 編曲 Agent。
- 不處理人聲、Bass、吉他及其他樂器的全面修復。
- 不讓使用者逐一手動搜尋、試聽及挑選 Sample 才能完成任務。
- 不為了整合而搬入其他專案的整套應用程式或大型依賴。
- 不在 V3 封版問題尚未釐清時，直接大改既有 Tempo / MIDI 匯出流程。

---

## 3. Drum Processing Policy

這是整個產品最重要的規格。鼓件分成兩種處理路徑，不得用同一套替換規則。

### 3.1 Kick / Snare / Tom — Original + Sample Layering

**處理方式：保留原始鼓聲，再疊加自動匹配的新 Sample。**

每次擊打至少分析：

- Onset / Transient：擊打起始位置及瞬態形狀。
- Pitch Curve：擊打後的音高變化曲線。
- Fundamental / Resonance：基頻、共振峰及主要諧波。
- Attack / Decay / Envelope：起音、衰減及能量包絡。
- Timbre / Spectral Profile：音色及頻譜特徵。
- Velocity：原始擊打力度。
- Polarity / Phase：極性、相位與時間對齊資訊。

#### Kick

優先匹配低頻基頻、Pitch Drop、Attack、Body、Decay 及低頻能量分布。不得只用單一靜態 Pitch 數值代表整個 Kick。

#### Snare

同時考慮 Body Resonance、Transient、Noise / Wire Character、頻譜重心及 Decay。Snare 具有寬頻噪聲特性，若無可靠穩定音高，不得強制套用單一 Pitch；應使用共振輪廓及音色特徵完成匹配。

#### Tom

優先分析 Fundamental、Pitch Envelope、Harmonics、Attack 與 Decay。依照不同 Tom 音域及擊打力度搜尋相近 Sample。

#### Layering Renderer

- 原始鼓聲保留為主要參考層。
- 新 Sample 依照匹配結果調整 Pitch、時間、增益及必要的 Envelope。
- 進行波形相關性、極性與相位檢查，避免疊加後低頻抵消或瞬態變薄。
- Velocity 必須影響 Sample Layer / Gain，不可將所有擊打渲染成同一力度。
- 支援原音與新 Sample 的比例調整；預設值需透過實際聆聽驗收決定。
- 不得為了追求更大聲而自動 Normalize 破壞原始動態。

### 3.2 Hi-Hat / Cymbals — Full Replacement

**處理方式：新 Sample 完整替換原始鼓聲。**

需要辨識：

- Closed / Open Hi-Hat。
- Short / Long / Choked articulation。
- Ride Bow / Bell 等不同演奏區域（來源素材能辨識時）。
- Crash 類型、Attack、Sustain、Decay。
- Velocity、擊打間距及尾音重疊關係。
- Stereo Width / Position（素材及來源資訊足夠時）。

替換時必須：

- 保留原始 Onset、Velocity 與 Microtiming。
- 避免 Open Hi-Hat 尾音被下一個 Closed Hit 不合理截斷。
- 正確處理 Crash / Ride 的長尾及重疊事件。
- 使用 Crossfade / Overlap-add 等適當方法避免切點爆音。
- 保留原本的演奏密度與 Articulation，不可把 Cymbal 全部量化成固定節奏。

**不得將 Cymbal / Hi-Hat 的處理簡化為一般鼓聲 Trigger。**

---

## 4. Target Architecture

採用單一 GrooveMap 核心、獨立模組、明確資料契約的架構。

```
Input Audio
  │
  ├── Full Mix / Existing Drum Stem
  │
  ▼
Separation Adapter
  │
  ├── Kick
  ├── Snare
  ├── Toms
  ├── Hi-Hat
  ├── Ride
  └── Crash
  │
  ▼
GrooveMap V3 Event Engine
  │
  ├── Beat / Tempo Map
  ├── Onset / Hit Events
  ├── Velocity
  └── Microtiming
  │
  ▼
V4 Acoustic Fingerprint Engine
  │
  ├── Pitch / Resonance Curve
  ├── Transient Profile
  ├── Timbre / Spectral Features
  ├── Attack / Decay / Envelope
  └── Articulation / Confidence
  │
  ▼
Local Sample Library Index
  │
  ▼
Intelligent Sample Matcher
  │
  ├── Drum Class Filter
  ├── Acoustic Similarity Ranking
  ├── Pitch / Velocity Compatibility
  ├── Kit Consistency
  └── Best Candidate Selection
  │
  ▼
Drum-specific Reconstruction Renderer
  │
  ├── Kick / Snare / Tom: Layering
  └── HH / Cymbals: Full Replacement
  │
  ▼
Quality Gate
  │
  ▼
WAV Stems + MIDI + Tempo Map + Preview
```

### 4.1 模組責任

| Module | Responsibility | Reuse / Build |
|---|---|---|
| Separation Adapter | 呼叫鼓件分離引擎、統一輸入輸出 | Adapter；優先接現成工具 |
| Drum Event Engine | Beat、Onset、Velocity、Tempo | 沿用 GrooveMap V3 |
| Acoustic Fingerprint | Per-hit Pitch、Timbre、Transient、Envelope | 新增薄模組 |
| Sample Library Index | 掃描、特徵計算、索引、快取 | 新增薄模組 |
| Intelligent Matcher | 候選搜尋、排序、Kit 一致性 | 新增核心模組 |
| Reconstruction Renderer | Layering / Replacement / Alignment | 新增核心模組 |
| Quality Gate | 檢查事件、聲音、輸出與品質 | 新增薄模組 |
| Export Adapter | WAV / MIDI / Tempo Map / DAW | 沿用並擴充既有匯出 |

建議模組邊界：

- separation adapter
- drum event analyzer
- acoustic fingerprint engine
- sample library index
- sample matcher
- reconstruction renderer
- reconstruction quality gate
- reconstruction export

以上為邏輯模組名稱，不代表已經建立相同名稱的檔案或目錄。實作前必須先對照 V3 實際程式碼，選擇最小接線位置。

---

## 5. Intelligent Sample Matcher — Product Core

### 5.1 Local Sample Library

使用者只需指定一次本地 Sample 資料夾。系統掃描音檔並建立可增量更新的索引，不要求使用者逐次搜尋。

索引至少包含：

- File Path / Hash / Duration / Sample Rate / Channels。
- Drum Class / Articulation。
- Pitch / Resonance Profile。
- Attack / Decay / Envelope。
- Spectral / Timbre Features。
- Velocity Layer / Round Robin Metadata（素材有提供時）。
- Stereo / Mono、Peak / RMS、Tail Length。
- Feature Extractor Version。

索引應使用輕量本地資料庫（初步採 SQLite），音訊特徵與檔案路徑分離保存。檔案變更時只重建受影響項目，不重新掃描整個素材庫。

### 5.2 Matching Pipeline

1. **Class Filter**：先排除錯誤鼓件、錯誤演奏法及不相容素材。
2. **Coarse Search**：以低成本聲學特徵快速縮小候選集合。
3. **Fine Ranking**：比較 Pitch / Resonance、Transient、Timbre、Envelope、Decay。
4. **Context Ranking**：考慮同一首歌的 Kit 音色一致性、Velocity Layer 與前後擊打關係。
5. **Render Evaluation**：將少量候選進行短片段試渲染，比較匹配後的聲學特徵。
6. **Automatic Selection**：選擇整體效果最佳者，不要求使用者手動挑選。
7. **Fallback**：信心不足或沒有合格候選時，保留原始鼓聲／不執行破壞性替換，並標記原因。

### 5.3 Matching Score

匹配分數應採鼓件專屬權重，不得以單一通用公式套用所有鼓件。

| Feature | Kick | Snare | Tom | Hi-Hat | Cymbal |
|---|---:|---:|---:|---:|---:|
| Pitch / Resonance | High | Medium | High | Low | Low |
| Transient | High | High | High | High | High |
| Timbre / Spectrum | High | High | High | Very High | Very High |
| Attack / Decay | High | High | High | Very High | Very High |
| Articulation | Medium | Medium | Medium | Very High | Very High |
| Velocity Compatibility | High | High | High | High | High |

權重及門檻必須由實際樣本資料集、盲聽 A/B 與錯誤案例調校後才定版。不可在尚未測試時宣稱有固定匹配準確率。

### 5.4 Kit Consistency

同一首歌曲的鼓組應維持一致的音色風格。

- 避免每次擊打都獨立選到完全不同的鼓。
- 優先建立每個 Drum Class 的候選 Kit / Sample Family。
- 允許依照 Velocity、Articulation、Pitch 區域使用不同 Layer。
- 有 Round Robin 素材時，才使用 Round Robin。
- 不可為了音色一致而犧牲原始擊打特徵及演奏法。

---

## 6. Acoustic Analysis & DSP Strategy

### 6.1 Per-hit Analysis

每次擊打建立獨立 Event Record，至少包含：

- event_id / source_stem / drum_class
- onset_time / onset_sample
- velocity_estimate / event_duration
- pitch_curve / fundamental_estimate / resonance_profile
- transient_profile / spectral_features
- attack / decay / envelope
- articulation / stereo_position（可取得時）
- analysis_confidence / warnings

Pitch 必須以時間變化曲線或分段特徵處理，尤其 Kick / Tom 的音高可能在擊打後快速下降。Snare、Cymbal 等非穩定音高來源，應允許使用 Resonance / Spectral Profile 取代不可靠的單一 Pitch。

### 6.2 Candidate Technology

優先評估成熟 DSP 函式庫及現有專案的可重用模組：

- librosa / SciPy：音高、頻譜、Envelope、訊號分析。
- Rubber Band 等 Time-Stretch / Pitch 工具：必須先確認授權與發行方式。
- SQLite：本地 Sample Metadata 與索引。
- NumPy / 向量化距離計算：初期相似度搜尋。
- HNSW 等近似近鄰索引：只有素材庫規模與效能測試證明必要時才加入。

不預設一定要導入 Embedding Model。先建立可解釋、可量測的 DSP Baseline，再比較 Embedding 是否能實際提升相似 Sample 的聽感匹配。

---

## 7. Reuse-First Project & OSS Strategy

以下為候選來源，不代表已完成整合或授權核准。

| Source | Potential Reuse | Decision |
|---|---|---|
| [GrooveMap V3 / PR #4](https://github.com/kevin781130-netizen/GrooveMap/pull/4) | Beat、Tempo、Onset、Velocity、MIDI、既有 Pipeline | 唯一產品基底 |
| [StemSplitter](https://github.com/hmcelik/stem-splitter) | 六種鼓件分離、CLI、Float WAV、Residual | 優先做 Adapter / UAT |
| [Automix](https://github.com/kevin781130-netizen/Automix) | 既有音訊特徵與 Suno 音訊瑕疵分析經驗 | 只挑選可獨立重用的 DSP 模組 |
| [HearScore](https://github.com/kevin781130-netizen/hear-score) | 鼓組視覺化、波形、頻譜及 MIDI UI 參考 | 只參考必要介面元件 |
| [FlowSonic](https://github.com/kevin781130-netizen/flowsonic) | 外部程序、Job、輸出與錯誤隔離 | 只參考薄型執行模式 |
| [SampleSpace](https://github.com/LukeMainwaring/samplespace) | Audio-to-Audio Similarity / Sample Matching 研究 | 候選研究，不預設整套採用 |
| [Subsample](https://github.com/simonholliday/subsample) | 聲學特徵與 Sample Mapping 研究 | AGPL-3.0；不直接搬入，除非另行核准授權策略 |
| [Glean](https://github.com/yonie/glean) | 音色指紋與相似度方法參考 | 先核實程式碼、授權及適用性 |

### 7.1 License Gate

任何外部程式碼、模型權重及 Sample 素材都必須分別審核：

- Source Code License。
- Model Weight License。
- Model Download / Redistribution Terms。
- Commercial Use / Derivative Work。
- Sample Library 的商用授權及再分發限制。
- 第三方程式執行方式、依賴、封裝及維護狀態。

**StemSplitter 的程式碼授權與其執行時下載的模型權重授權是兩件事。** 即使程式碼可採 MIT 使用，也不得因此推定所有模型權重都可商用。

---

## 8. Output Specification

### 8.1 Audio Deliverables

- Reconstructed Kick WAV。
- Reconstructed Snare WAV。
- Reconstructed Toms WAV。
- Reconstructed Hi-Hat WAV。
- Reconstructed Ride WAV。
- Reconstructed Crash WAV。
- Reconstructed Drum Bus / Drum Stem。
- Optional Original / Replaced / Layered A-B Preview。

輸出優先保留來源 Sample Rate、Channel Layout、時間起點及必要的原始動態資訊。禁止未經使用者要求就 Normalize 或覆寫原始音訊。

### 8.2 MIDI / DAW Deliverables

- Drum MIDI：原始擊打時間、Velocity、Drum Class Mapping。
- Tempo Map：沿用 GrooveMap V3 的 Tempo / Beat 資訊。
- WAV Stems：與原曲時間軸對齊，可直接匯入 Cubase。
- Processing Report：來源、Sample Mapping、Pitch / Timing / Gain / Phase 處理紀錄。
- Quality Report：低信心事件、未替換事件、失敗原因及測試結果。

---

## 9. Quality Gate & Acceptance Criteria

### 9.1 Functional Acceptance

- 可輸入完整歌曲或既有 Drum Stem。
- 可輸出六種鼓件分軌；分離失敗時能明確回報，不得假裝成功。
- 原始 Beat / Tempo / Onset / Velocity 能保留並可追溯。
- Kick / Snare / Tom 走 Layering 路徑。
- Hi-Hat / Cymbals 走 Full Replacement 路徑。
- Sample Library 可建立、更新及重用索引。
- 系統能自動完成 Sample 搜尋、排序及選擇。
- 使用者不需要手動挑選 Sample 才能完成預設工作流程。
- 沒有合格 Sample 時，能安全回退並保留原始聲音。
- 所有輸出與原始歌曲時間軸對齊。

### 9.2 Audio Quality Acceptance

必須建立真實測試集，至少涵蓋：

- 不同 BPM、拍號與變速歌曲。
- 不同風格、鼓組音色及密度。
- Kick / Snare / Tom 的不同音高與力度。
- Ghost Notes、Roll、Flam、Fill、Open / Closed Hi-Hat。
- Ride / Crash 長尾與重疊擊打。
- 分離殘留、Cymbal Bleed、混合音源及低信心事件。

量測項目：

- Onset Timing Error。
- Hit Detection Precision / Recall / F1。
- Velocity Correlation。
- Pitch / Resonance Matching Error（只對可可靠估計的鼓件評估）。
- Transient / Envelope Similarity。
- Phase / Polarity / Clipping / Peak / RMS 檢查。
- 原始 Groove 保留程度。
- 人工盲聽 A/B：是否比原始 AI 鼓組更乾淨、有力，且沒有明顯偏離原曲音色。

**所有量化門檻必須先建立 V3 / 原始音訊 Baseline，再由真實測試資料訂定；沒有測試證據不得標記 PASS。**

### 9.3 Regression Acceptance

- V3 原有 WAV / AIFF 輸入及 Tempo / Click / Marker / Cubase MIDI 匯出不得退化。
- 新增模組不得破壞既有 Tempo Map、MIDI Tick、事件排序及時間對齊。
- Windows GUI / CLI 必須實機驗收。
- macOS 作為第二平台，另列相容性與效能結果。
- 測試報告必須區分 PASS / FAIL / NOT_RUN。

---

## 10. Development Roadmap — Knife 1–8

| Knife | Scope | Deliverable | Exit Gate |
|---|---|---|---|
| 0 | V3 基底鎖定 | PR / Branch / SHA / License / Test Baseline | 確認唯一正確 V3 起點 |
| 1 | Drum Separation Adapter | 六鼓件分離、Float WAV、時間軸及 Residual 驗證 | Windows 5090 分離測試 PASS |
| 2 | Per-hit Acoustic Analyzer | Pitch / Resonance / Transient / Timbre / Envelope | 有標註樣本及分析測試 |
| 3 | Local Sample Library | 掃描、指紋、SQLite、增量索引 | 可重複索引與檢索 |
| 4 | Intelligent Sample Matcher | 多維相似度、候選排序、Kit Consistency | 盲聽匹配基準達標 |
| 5 | Reconstruction Renderer | Kick / Snare / Tom Layering；HH / Cymbal Replacement | 無明顯錯位、相位抵消、切點爆音 |
| 6 | Quality Gate | 自動品質檢查、低信心回退、報告 | 失敗案例可定位、可重現 |
| 7 | UI / Export | 一鍵重建、A/B、WAV / MIDI / Tempo Map | 完整工作流可交付 |
| 8 | Hardware UAT | RTX 5090 Windows、macOS、Cubase | 實機驗收及封版證據 |

每個 Knife 必須獨立測試、保留可回退的 Git 狀態；未通過前不得直接進入下一個階段。

---

## 11. Implementation Constraints

### 11.1 Repository / Branch Policy

- 唯一產品 Repository：GrooveMap。
- 不建立第二個 Drum Restoration Repository。
- 不直接修改 main 進行功能開發。
- V3 PR #4 目前是 Draft，尚未合併；不可假設 main 已包含 V3。
- Knife 0 必須重新核對 PR #4 的 Head SHA、父分支、測試結果及目前工作樹。
- V4 實作分支應從經確認的 V3 開發基底建立，而不是盲目從舊 main 開始。
- V3 封版待修清單仍由 [Issue #5](https://github.com/kevin781130-netizen/GrooveMap/issues/5) 管理；V4 研發不得混入 V3 封版阻塞項目。

### 11.2 Runtime / Packaging

- 優先 Windows 11 + NVIDIA CUDA。
- 第一階段以 RTX 5090 實測 VRAM、速度及長時間穩定性。
- 分離模型採外部 Adapter，不將特定模型深度耦合至 GrooveMap 核心。
- Sample Library 使用者自行指定路徑，避免複製大量素材。
- 所有 Job 支援取消、失敗紀錄及安全輸出。
- macOS 支援列為後續相容性驗收，不得假設 Windows CUDA 路徑可直接移植。

### 11.3 Performance Goals

初期不承諾固定處理速度。Knife 1 必須記錄：

- 分離模型及版本。
- 音訊長度、取樣率、聲道數。
- GPU / VRAM 使用量。
- 每階段耗時。
- Sample Library 數量及索引耗時。
- 單次 Matcher 查詢耗時。
- 完整歌曲重建耗時及失敗率。

先建立可重現 Benchmark，再決定效能目標。

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Drum Separation Bleed | 鼓件誤觸發、匹配錯誤 | 保留 Residual、事件信心與人工標註測試 |
| Pitch Estimation Error | 找到錯誤音高 Sample | Pitch Curve + Resonance Profile + Confidence |
| Similarity Score 不等於聽感 | 自動挑到數值相近但不好聽的 Sample | 多特徵匹配、短片段渲染、盲聽 A/B |
| Phase Cancellation | 疊加後變薄或低頻消失 | Polarity / Phase / Correlation Gate |
| Cymbal Tail Overlap | 尾音斷裂或重疊失真 | Articulation / Tail / Crossfade 處理 |
| Kit Inconsistency | 同一首歌鼓組音色跳動 | Kit-level Matching / Velocity Layer |
| Model / Sample Licensing | 商業發行風險 | Source / Weight / Sample 三層授權審核 |
| V3 Base Not Released | 新功能建在錯誤基底 | Knife 0 鎖定 SHA，保留 V3 分支鏈 |

---

## 13. Definition of Done

GrooveMap V4 只有在以下條件全部成立後，才可宣稱完成：

1. 使用者能輸入 Suno 歌曲或 Drum Stem。
2. 系統能分離及分析六種鼓件。
3. 系統能對每次擊打取得足夠可靠的聲學特徵。
4. 系統能從本地 Sample Library 自動選出接近原始鼓聲的素材。
5. Kick / Snare / Tom 自動疊加，原始演奏與音色特色仍可辨識。
6. Hi-Hat / Cymbal 自動完整替換，Articulation 及尾音自然。
7. 不需要使用者手動搜尋 Sample 才能完成工作。
8. 重建結果在盲聽 A/B 中具備可驗證的音質改善。
9. WAV / MIDI / Tempo Map 可正確交付 Cubase。
10. Windows 5090 實機驗收完成，macOS 相容性結果獨立記錄。
11. V3 原有功能回歸測試 PASS。
12. 授權、依賴、模型權重及 Sample 素材使用條件已審核。

---

## 14. Current Status & Next Action

**Current status：PROPOSED / NOT IMPLEMENTED**

本文件只定義產品方向、技術架構、模組邊界及驗收標準。尚未修改 GrooveMap 原始程式碼，尚未整合 StemSplitter，尚未下載模型權重，也沒有宣稱任何 V4 功能已完成。

### 下一個正式任務：Knife 0 — V3 Baseline Lock

1. 核對 GrooveMap PR #4 的實際 Head SHA 與分支鏈。
2. 核對 V3 現有程式碼、測試、輸出契約及未提交變更。
3. 確認 StemSplitter 程式碼、模型權重及依賴授權。
4. 建立六鼓件分離的真實 Suno 測試樣本與基準報告。
5. 完成後才進入 Knife 1 Adapter 接線。

**本企劃的最高優先級是自動 Sample Matching 的聽感準確度。** 分離、偵測、MIDI、渲染都是必要基礎，但不能取代這個核心差異化能力。

---

## References

- [GrooveMap Repository](https://github.com/kevin781130-netizen/GrooveMap)
- [GrooveMap V3 RC — Draft PR #4](https://github.com/kevin781130-netizen/GrooveMap/pull/4)
- [GrooveMap V3 Release Checklist — Issue #5](https://github.com/kevin781130-netizen/GrooveMap/issues/5)
- [StemSplitter](https://github.com/hmcelik/stem-splitter)
- [Automix](https://github.com/kevin781130-netizen/Automix)
- [HearScore](https://github.com/kevin781130-netizen/hear-score)
- [FlowSonic](https://github.com/kevin781130-netizen/flowsonic)
- [SampleSpace](https://github.com/LukeMainwaring/samplespace)
- [Subsample](https://github.com/simonholliday/subsample)
- [Glean](https://github.com/yonie/glean)
