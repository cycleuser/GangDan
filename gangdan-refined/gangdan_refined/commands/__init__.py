"""CLI commands for GangDan Refined.

Each command is an independent tool that can be composed in pipelines.
All commands support --json for machine-readable output.

Commands:
    gd-chat        Send a message to an LLM
    gd-search      Search the web or academic papers
    gd-kb          Manage knowledge bases (CRUD, search, index)
    gd-docs        Download and index documentation
    gd-config      View and modify configuration
    gd-translate   Translate text between languages
    gd-summarize   Summarize text with an LLM
    gd-ask         Ask a question against knowledge base (RAG)
    gd-embed       Generate text embeddings
    gd-models      List available LLM models
    gd-convert     Convert PDF/CAJ to Markdown
    gd-web         Start the web server
"""