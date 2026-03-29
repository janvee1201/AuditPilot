auditpilot/
│
├── main.py                        ← master entry point, runs everything
│
├── auditpilot.db                  ← SQLite database (created by init_db.py)
├── init_db.py                     ← run once to create all tables + seed data
│
├── shared/                        ← shared utilities used by all agents
│   ├── __init__.py
│   ├── db.py                      ← single SQLite connection function
│   ├── error_map.py               ← maps all agent error strings to W4 hashes
│   └── logger.py                  ← shared log formatter (moved from W1/utils)
│
├── data/                          ← all JSON input files
│   ├── clients.json               ← W1 input
│   ├── existing_clients.json      ← W1 duplicate check
│   ├── existing_clients.seed.json ← W1 demo reset seed
│   ├── purchase_orders.json       ← W2 input
│   ├── vendors.json               ← W2 vendor lookup
│   └── team_members.json          ← W3 owner resolution
│
├── w1/                            ← W1 client onboarding agent
│   ├── __init__.py
│   ├── graph.py                   ← LangGraph StateGraph definition
│   ├── state.py                   ← W1 State TypedDict
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── validation.py          ← T1 validate node
│   │   ├── duplicate.py           ← T2 duplicate check node
│   │   ├── kyc.py                 ← T3 KYC verify node
│   │   ├── execution.py           ← T4 create account node
│   │   └── error.py               ← error node — calls W4
│   └── utils/
│       ├── __init__.py
│       └── hitl.py                ← human in the loop prompts
│
├── w2/                            ← W2 procurement to payment agent
│   ├── __init__.py
│   ├── graph.py                   ← LangGraph StateGraph definition
│   ├── state.py                   ← W2 State TypedDict
│   └── nodes/
│       ├── __init__.py
│       ├── intake.py              ← intake node
│       ├── validation.py          ← invoice vs PO match node
│       ├── vendor_check.py        ← vendor lookup node
│       ├── approval.py            ← approval node
│       ├── payment.py             ← payment node
│       ├── monitor.py             ← monitor node
│       ├── orchestrator.py        ← orchestrator node — calls W4
│       └── audit.py               ← audit node
│
├── w3/                            ← W3 meeting to task agent
│   ├── __init__.py
│   ├── pipeline.py                ← main run_meeting_agent() function
│   └── nodes/
│       ├── __init__.py
│       ├── intake.py              ← intake_agent()
│       ├── extraction.py          ← extraction_agent() — calls LLM
│       ├── owner_resolution.py    ← resolve_owner() — calls W4 on ambiguous
│       └── task_writer.py         ← writes tasks to SQLite
│
├── w4/                            ← W4 cross-workflow pattern memory agent
│   ├── __init__.py
│   └── agent.py                   ← all W4 functions: T13, T14, T15, T16
│                                     run_w4(), write_trace()
│
└── orchestrator/                  ← master orchestrator
    ├── __init__.py
    ├── graph.py                   ← LangGraph StateGraph for master flow
    ├── state.py                   ← MasterState TypedDict
    └── nodes/
        ├── __init__.py
        ├── intent_classify.py     ← calls Claude API to classify task
        ├── clarification.py       ← asks user if confidence is low
        ├── state_builder.py       ← builds workflow initial state from params
        ├── invoke_workflows.py    ← calls W1/W2/W3 graph or pipeline
        └── result_builder.py      ← builds plain-English reply for frontend