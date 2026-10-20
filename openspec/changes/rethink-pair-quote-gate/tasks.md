## 1. 配置与注释

- [x] 1.1 增加 `PAIR_ASK_MIN`（默认 0.38）、`PAIR_ASK_MAX`（默认 0.62）、`RESIDUAL_JOIN_MAX_UNDER_BE`（默认 0.15）；`.env` 注明不可把配对带设成双进 0.6～0.68
- [x] 1.2 建议关闭或放宽单边 `MIN_ASK`/`MAX_ASK` 以免与配对带叠出「只挂一边」；`load_config` 读入并打启动日志

## 2. 平衡仓配对门禁

- [x] 2.1 去掉「必须双进 (0.6,0.68]」类逻辑；改为涨跌算价都 ∈[PAIR_MIN,PAIR_MAX] 才挂，否则两边都不挂
- [x] 2.2 用例：0.64/0.42 不挂；0.53/0.53 可挂；残腿模式仍可只挂重仓侧

## 3. 残腿 join 门禁

- [x] 3.1 `be_join` 前若 `P_be - join_price > RESIDUAL_JOIN_MAX_UNDER_BE` 则不挂并冻结该窗残腿报价
- [x] 3.2 用例：对照 15:25（P_be≈0.35、join≈0.05）必须拦截；join≈0.25 且阈值 0.15 时仍可 join
