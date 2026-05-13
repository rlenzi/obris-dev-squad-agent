"""Demo manual da Fase 3.1a: roda um agente Dev-Backend numa task simples.

Cenario: indexa o repo do reco-orbis (se ainda nao tiver), depois roda um
agente com a pergunta 'explique a arquitetura do backend'. O agente usa
retrieve_knowledge + read_file pra investigar e signal_complete pra fechar.

NAO faz mudancas em codigo (escrita vem na 3.1b). Aqui validamos:
- Loop tool_use funciona com Claude
- retrieve_knowledge integra com Retriever
- read_file le do workspace
- Cost tracking grava ExternalApiCall
- Manifest enforcer bloquearia se algo saisse do escopo
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select

from dev_autonomo.agent_runtime.context import AgentRunContext
from dev_autonomo.agent_runtime.enforcement import ManifestEnforcer
from dev_autonomo.agent_runtime.toolset.base import ToolRegistry
from dev_autonomo.agent_runtime.toolset.basic import (
    ReadFileTool,
    RetrieveKnowledgeTool,
    SignalCompleteTool,
)
from dev_autonomo.agent_runtime.worker import AgentRunner
from dev_autonomo.common.claude_client import ClaudeClient
from dev_autonomo.db.models import Client, Squad
from dev_autonomo.db.session import session_scope
from dev_autonomo.knowledge.indexer import CodeIndexer
from dev_autonomo.knowledge.qdrant_client import (
    KnowledgePartition,
    QdrantKnowledgeStore,
)
from dev_autonomo.knowledge.retriever import KnowledgeRetriever
from dev_autonomo.knowledge.voyage_client import VoyageEmbeddingClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
# Silencia ruido SQL
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

REPO_LOCAL = Path("/home/rubens/dev-autonomo-workspace/reference-only/produto-backend")
REPO_LABEL = "https://github.com/rlenzi/reco.orbis.ai.api.git"

SYSTEM_PROMPT = """\
Voce e um Dev Backend Python+FastAPI senior trabalhando na squad Reco Orbis.
Seu objetivo nesta task: investigar o codebase para responder a pergunta do
usuario com precisao.

Use as tools disponiveis:
- retrieve_knowledge: encontra trechos relevantes do codigo via busca semantica
- read_file: le um arquivo especifico (depois que o retrieve apontar onde olhar)
- signal_complete: chame quando tiver respondido a pergunta com qualidade

Nao especule sem evidencia. Cite arquivos e linhas. Se faltar contexto, busca mais.
"""


async def ensure_indexed(squad_id, client_id):
    """Indexa o backend se a collection ainda nao tiver pontos."""
    store = QdrantKnowledgeStore()
    name = store.collection_name(KnowledgePartition.CODE, squad_id)
    try:
        # collection_exists levanta se nao existir
        if await store._client.collection_exists(name):
            count = await store.count(KnowledgePartition.CODE, squad_id)
            if count > 0:
                print(f"Collection {name} ja tem {count} chunks, pulando indexacao.")
                await store.close()
                return
    except Exception:
        pass

    print(f"Indexando {REPO_LOCAL} ...")
    voyage = VoyageEmbeddingClient()
    indexer = CodeIndexer(voyage=voyage)
    result = await indexer.index_repo(
        client_id=client_id,
        squad_id=squad_id,
        repo_path=REPO_LOCAL,
        repo_label=REPO_LABEL,
    )
    print(
        f"  {result.chunks_created} chunks indexados, "
        f"US$ {result.embedding_cost_usd:.4f}, {result.duration_seconds:.1f}s"
    )
    await store.close()


async def main():
    async with session_scope() as session:
        client = (
            await session.execute(select(Client).where(Client.slug == "reco-orbis"))
        ).scalar_one()
        squad = (
            await session.execute(select(Squad).where(Squad.client_id == client.id))
        ).scalar_one()

        await ensure_indexed(squad.id, client.id)

        # Monta contexto
        voyage = VoyageEmbeddingClient(session=session)
        qdrant = QdrantKnowledgeStore()
        retriever = KnowledgeRetriever(session=session, voyage=voyage, qdrant=qdrant)
        enforcer = ManifestEnforcer(
            session=session, client_id=client.id, squad_id=squad.id
        )
        ctx = AgentRunContext(
            client_id=client.id,
            squad_id=squad.id,
            agent_instance_id=None,  # fase 3.1a: ainda sem agent_instance real (cost vai pro client_id)
            task_id=None,
            session=session,
            claude=ClaudeClient(session=session),
            voyage=voyage,
            qdrant=qdrant,
            retriever=retriever,
            enforcer=enforcer,
            workspace_root=REPO_LOCAL,
        )

        # Registra tools
        registry = ToolRegistry()
        registry.register(RetrieveKnowledgeTool())
        registry.register(ReadFileTool())
        registry.register(SignalCompleteTool())

        runner = AgentRunner(ctx=ctx, registry=registry, model="claude-haiku-4-5", max_turns=20)

        # ----- Task ----
        user_prompt = (
            "Investigue como esta organizado o sistema de autenticacao e rate "
            "limit nesta API FastAPI. Quais endpoints fazem login? Que mecanismo "
            "de rate limiting esta em uso? Responda com referencias concretas "
            "(arquivo e linhas)."
        )

        print("\n" + "=" * 60)
        print("Iniciando agente...")
        print("=" * 60)
        result = await runner.run(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            enabled_tools=["retrieve_knowledge", "read_file", "signal_complete"],
        )

        print("\n" + "=" * 60)
        print("RESULTADO")
        print("=" * 60)
        print(f"completed:       {result.completed}")
        print(f"turnos:          {result.turn_count}")
        print(f"tool calls:      {len(result.tool_calls)}")
        print(f"  sequencia:     {' -> '.join(result.tool_calls)}")
        print(f"custo total:     US$ {result.total_cost_usd:.4f}")
        if result.error:
            print(f"erro:            {result.error}")
        print()
        if result.completion_summary:
            print("SUMARIO DO AGENTE:")
            print(result.completion_summary)
            if result.completion_deliverables:
                print("\nDELIVERABLES:")
                for d in result.completion_deliverables:
                    print(f"  - {d}")
        elif result.final_text:
            print("RESPOSTA FINAL:")
            print(result.final_text[:2000])

        await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
