# -*- coding: utf-8 -*-
"""D1 SQLite 账本骨架包（标准库 sqlite3，无第三方依赖）。

- connection.py：连接工厂 / pragmas / 单写事务
- migrate.py   ：Migration runner（CLI：python3 -m db.migrate）
- repository.py：数据访问（纯 SQL，不写业务规则）
- service.py   ：业务规则（校验、幂等、持仓重建、现金追加）
- api.py       ：/api/ledger/* JSON API 路由
- valution.py  ：D4 估值回撤双源核验（只读算法，不写库）

约定：只有人工核实“已成交/已卖出成交”的记录可写 transactions.confirmed=1；
持仓由 confirmed 交易聚合重建；现金为追加式事件账本。
"""

__all__ = ["connection", "migrate", "repository", "service", "api"]
