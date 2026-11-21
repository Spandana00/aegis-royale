"""Canonical source-audit representation, independent of ast.dump formatting."""
import ast
import json


def stable_ast_dump(tree):
    def normalize(value):
        if isinstance(value,ast.AST):
            return [type(value).__name__,[[name,normalize(child)]
                    for name,child in ast.iter_fields(value) if child is not None]]
        if isinstance(value,list):
            return [normalize(child) for child in value]
        if value is None or isinstance(value,(str,int,float,bool)):
            return value
        return ['literal',type(value).__name__,repr(value)]
    return json.dumps(normalize(tree),ensure_ascii=True,separators=(',',':'))
