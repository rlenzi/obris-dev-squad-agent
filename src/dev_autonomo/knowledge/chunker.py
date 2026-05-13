"""Chunker semantico via tree-sitter: extrai funcoes, classes, types como chunks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import tree_sitter_python as ts_python
import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Node, Parser


class ChunkKind(StrEnum):
    MODULE = "module"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    TYPE = "type"
    INTERFACE = "interface"


@dataclass(slots=True)
class CodeChunk:
    kind: ChunkKind
    name: str
    content: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    signature: str | None = None
    parent: str | None = None


SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
}


class CodeChunker:
    """Parser AST e chunker semantico para Python e TypeScript/TSX."""

    def __init__(self) -> None:
        self._py_lang = Language(ts_python.language())
        self._ts_lang = Language(ts_typescript.language_typescript())
        self._tsx_lang = Language(ts_typescript.language_tsx())

        self._parsers: dict[str, Parser] = {
            "python": Parser(self._py_lang),
            "typescript": Parser(self._ts_lang),
            "tsx": Parser(self._tsx_lang),
            "javascript": Parser(self._tsx_lang),
        }

    def language_for(self, file_path: str | Path) -> str | None:
        ext = Path(file_path).suffix.lower()
        return SUPPORTED_EXTENSIONS.get(ext)

    def chunk_file(self, file_path: str | Path, content: bytes | None = None) -> list[CodeChunk]:
        path = Path(file_path)
        language = self.language_for(path)
        if language is None:
            return []

        if content is None:
            content = path.read_bytes()

        parser = self._parsers[language]
        tree = parser.parse(content)

        if language == "python":
            return self._chunk_python(tree.root_node, content, str(path), language)
        return self._chunk_typescript(tree.root_node, content, str(path), language)

    # ------- Python -------

    def _chunk_python(self, root: Node, source: bytes, file_path: str, language: str) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        for child in root.children:
            self._walk_python_node(child, source, file_path, language, chunks, parent=None)
        return chunks

    def _walk_python_node(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        language: str,
        chunks: list[CodeChunk],
        parent: str | None,
    ) -> None:
        if node.type == "function_definition":
            name = self._py_name(node)
            chunks.append(
                CodeChunk(
                    kind=ChunkKind.METHOD if parent else ChunkKind.FUNCTION,
                    name=name,
                    content=source[node.start_byte : node.end_byte].decode(errors="replace"),
                    file_path=file_path,
                    language=language,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=self._py_signature(node, source),
                    parent=parent,
                )
            )
        elif node.type == "class_definition":
            name = self._py_name(node)
            chunks.append(
                CodeChunk(
                    kind=ChunkKind.CLASS,
                    name=name,
                    content=source[node.start_byte : node.end_byte].decode(errors="replace"),
                    file_path=file_path,
                    language=language,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    parent=None,
                )
            )
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    self._walk_python_node(child, source, file_path, language, chunks, parent=name)
        elif node.type == "decorated_definition":
            for child in node.children:
                if child.type in ("function_definition", "class_definition"):
                    self._walk_python_node(child, source, file_path, language, chunks, parent=parent)

    def _py_name(self, node: Node) -> str:
        name_node = node.child_by_field_name("name")
        return name_node.text.decode() if name_node is not None else "<anonymous>"

    def _py_signature(self, node: Node, source: bytes) -> str | None:
        name_node = node.child_by_field_name("name")
        params_node = node.child_by_field_name("parameters")
        if name_node is None or params_node is None:
            return None
        name = name_node.text.decode()
        params = source[params_node.start_byte : params_node.end_byte].decode(errors="replace")
        return f"def {name}{params}"

    # ------- TypeScript / TSX -------

    def _chunk_typescript(
        self, root: Node, source: bytes, file_path: str, language: str
    ) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        for child in root.children:
            self._walk_ts_node(child, source, file_path, language, chunks, parent=None)
        return chunks

    def _walk_ts_node(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        language: str,
        chunks: list[CodeChunk],
        parent: str | None,
    ) -> None:
        if node.type == "function_declaration":
            chunks.append(
                self._mk_chunk(ChunkKind.FUNCTION, self._ts_name(node), node, source, file_path, language, parent)
            )
        elif node.type == "class_declaration":
            name = self._ts_name(node)
            chunks.append(self._mk_chunk(ChunkKind.CLASS, name, node, source, file_path, language, None))
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    if child.type == "method_definition":
                        chunks.append(
                            self._mk_chunk(
                                ChunkKind.METHOD,
                                self._ts_name(child),
                                child,
                                source,
                                file_path,
                                language,
                                name,
                            )
                        )
        elif node.type == "interface_declaration":
            chunks.append(
                self._mk_chunk(ChunkKind.INTERFACE, self._ts_name(node), node, source, file_path, language, parent)
            )
        elif node.type == "type_alias_declaration":
            chunks.append(
                self._mk_chunk(ChunkKind.TYPE, self._ts_name(node), node, source, file_path, language, parent)
            )
        elif node.type == "lexical_declaration":
            for declarator in node.named_children:
                if declarator.type == "variable_declarator":
                    name_node = declarator.child_by_field_name("name")
                    value_node = declarator.child_by_field_name("value")
                    if name_node is None or value_node is None:
                        continue
                    name = name_node.text.decode(errors="replace")
                    if value_node.type in ("arrow_function", "function_expression"):
                        chunks.append(
                            self._mk_chunk(
                                ChunkKind.FUNCTION, name, node, source, file_path, language, parent
                            )
                        )
        elif node.type == "export_statement":
            for child in node.children:
                self._walk_ts_node(child, source, file_path, language, chunks, parent)

    def _ts_name(self, node: Node) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return "<anonymous>"
        return name_node.text.decode(errors="replace")

    def _mk_chunk(
        self,
        kind: ChunkKind,
        name: str,
        node: Node,
        source: bytes,
        file_path: str,
        language: str,
        parent: str | None,
    ) -> CodeChunk:
        return CodeChunk(
            kind=kind,
            name=name,
            content=source[node.start_byte : node.end_byte].decode(errors="replace"),
            file_path=file_path,
            language=language,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent=parent,
        )
