# 為什麼「深度」會改變答案

同一個問題：「幫我回絕一個不合理的案子。」三種系統都能寫出通順文字；差別在於，它有沒有足夠依據判斷要守住什麼、怎麼說，以及哪些地方仍只是待驗證的行為模式。

| 通用 LLM 回答 | FAQ 式人格檔回答 | VirtualMe archive 驅動的回答 |
|---|---|---|
| 「謝謝你的邀請。考量目前資源有限，我恐怕無法承接這個案子，希望未來還有合作機會。」<br><br>**差異來源：**只根據這次問題，禮貌但沒有特定取捨。 | 「謝謝邀請，這案子目前不符合我的工作安排，我先婉拒；之後有合適機會再合作。」<br><br>**差異來源：**套用表單裡的「直接、簡短」，但不知道為何拒絕，也沒有可追查的情境證據。 | 「這個案子的範圍、預算和時程目前對不上，我不能照原案承諾。你可以選：縮小範圍，或調整預算／時程。」<br><br>**差異來源：**把 archive 裡的價值取捨、拒絕邊界與實際語氣樣本組成一份可人工確認的草稿。 |

VirtualMe 欄只用了這份合成 archive 已存在的內容：

- [`SOUL.md`](SOUL.md)：「Across the synthetic interviews, commitments that lock scope, price, or delivery dates appear to be treated as expensive decisions; the maker slows down before promising all three.」
- [`VOICE.md`](VOICE.md)：「One synthetic answer suggested a direct but not hostile register:『這個條件目前對不上，我不能照原案承諾。』」另一筆 recurring pattern 是「refusals tended to name the constraint mismatch in one sentence, then offer two concrete options instead of a long apology.」
- [`BOUNDARIES.md`](BOUNDARIES.md)：「Within one synthetic session, requests that exceed the agreed scope were repeatedly refused unless scope, budget, or timeline changed.」它仍是 **Recurring but Unvalidated**，所以答案應視為待本人 review 的 draft，而不是定論。

## 怎麼驗收：Week 5／8 盲評 gate

Week 5 把三種答案去掉來源標籤，請本人與教練盲評：哪一份更能守住邊界、說清取捨、維持自然語氣，也能指出「不像我」的句子。Week 8 換新情境再做一次。只有 archive 驅動答案能持續比 FAQ 式回答更貼近上述行為訊號，且不把未驗證模式說成定論，才算通過 demo gate。
