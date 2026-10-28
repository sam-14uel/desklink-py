# DeskLink – Project layout

```
desklink/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── examples/
│   └── config.yaml
├── src/
│   └── desklink/
│       ├── __init__.py
│       ├── cli/
│       │   └── main.py
│       ├── server/
│       │   └── __init__.py
│       ├── filesystem/
│       │   └── __init__.py
│       ├── tunnel/
│       │   └── __init__.py
│       ├── auth/
│       │   └── __init__.py
│       ├── config/
│       │   └── __init__.py
│       └── models/
│           └── __init__.py
└── tests/
    └── test_basic.py
```

All core components are modular for future expansion (additional MCP servers, tunnel providers, stronger auth, DeskLink cloud platform).
