"""Ask agent — RAG-based question answering over knowledge bases."""

from __future__ import annotations

from .base import BaseAgent, AgentInput, AgentOutput, AgentMetadata


class AskAgent(BaseAgent):
    name = "gd-ask"
    description = "Ask questions using RAG over knowledge bases"
    version = "2.0.0"

    def run(self, input: AgentInput) -> AgentOutput:
        question = input.query or input.text or ""
        kb_names = input.options.get("kb_names", [])
        top_k = input.options.get("top_k", 5)
        model = input.options.get("model", "")
        provider = input.options.get("provider", "")
        language = input.options.get("language", "")

        if not question:
            return AgentOutput(success=False, error="Question required", metadata=AgentMetadata(agent=self.name, version=self.version))

        if isinstance(kb_names, str):
            kb_names = [kb_names]

        try:
            client, model_name = self._get_llm_client(provider=provider, model=model)
            chroma = self._get_chroma()

            context_parts = []
            search_results = []
            for kb_name in kb_names:
                if chroma is not None and hasattr(chroma, "collection_exists") and chroma.collection_exists(kb_name):
                    results = chroma.search(kb_name, question, n_results=top_k)
                    search_results.extend(results)
                    for r in results:
                        if isinstance(r, dict) and r.get("content"):
                            context_parts.append(r["content"])

            context = "\n\n".join(context_parts[:5]) if context_parts else ""
            system_prompt = "Answer the question based on the provided context. If the context is insufficient, say so."
            if language:
                system_prompt += f" Respond in {language}."

            messages = []
            if context:
                messages.append({"role": "system", "content": f"{system_prompt}\n\nContext:\n{context}"})
            else:
                messages.append({"role": "system", "content": system_prompt})

            messages.append({"role": "user", "content": question})

            answer = client.chat(messages=messages, model=model_name)

            return AgentOutput(
                success=True,
                data={"answer": answer, "question": question, "kb_names": kb_names, "model": model_name, "context_used": len(context_parts), "sources_count": len(search_results)},
                metadata=AgentMetadata(agent=self.name, version=self.version),
            )
        except Exception as e:
            return AgentOutput(success=False, error=str(e), metadata=AgentMetadata(agent=self.name, version=self.version))

    def add_arguments(self, parser) -> None:
        self.add_common_args(parser)
        parser.add_argument("question", nargs="?", default="", help="Question to ask")
        parser.add_argument("--stdin", action="store_true", help="Read question from stdin")
        parser.add_argument("--kb", "-k", nargs="+", default=[], help="Knowledge base name(s)")
        parser.add_argument("--top-k", type=int, default=5, help="Number of context chunks to retrieve")
        parser.add_argument("--model", "-m", default="", help="Model to use")
        parser.add_argument("--provider", "-p", default="", help="LLM provider")
        parser.add_argument("--api-key", default="", help="API key")

    def build_input(self, args) -> AgentInput:
        return AgentInput(
            query=args.question,
            options={"kb_names": args.kb, "top_k": args.top_k, "model": args.model, "provider": args.provider, "api_key": args.api_key},
            metadata=AgentMetadata(agent=self.name, version=self.version),
        )