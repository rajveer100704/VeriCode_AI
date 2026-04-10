import ast
from typing import List, Dict, Set
from vericode_ai.schema.doc_chunk import DocChunk

class ValidationError:
    def __init__(self, message: str, line: int, symbol: str):
        self.message = message
        self.line = line
        self.symbol = symbol

    def to_dict(self):
        return {
            "message": self.message,
            "line": self.line,
            "symbol": self.symbol,
        }

class APISpec:
    """
    Extracts known API symbols + signatures from DocChunks
    """
    def __init__(self, chunks: List[DocChunk]):
        self.symbols: Set[str] = set()
        self.signatures: Dict[str, str] = {}

        for chunk in chunks:
            if chunk.symbol:
                # Add base symbol name (e.g. 'torch.relu' -> 'relu')
                short_name = chunk.symbol.split('.')[-1]
                self.symbols.add(chunk.symbol)
                self.symbols.add(short_name)
                
                self.signatures[chunk.symbol] = chunk.signature
                self.signatures[short_name] = chunk.signature


class CallVisitor(ast.NodeVisitor):
    """
    Extract function calls from AST
    """
    def __init__(self):
        self.calls = []

    def visit_Call(self, node: ast.Call):
        func_name = self._get_func_name(node.func)
        if func_name:
            self.calls.append((func_name, node.lineno, node))
        self.generic_visit(node)

    def _get_func_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr  # e.g., torch.relu → relu
        return None

class ASTValidator:
    """
    Validates code against known API spec extracted from Ground-Truth docs.
    """
    def __init__(self, chunks: List[DocChunk]):
        self.api_spec = APISpec(chunks)

    def validate(self, code: str) -> List[ValidationError]:
        errors = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [ValidationError(f"Syntax Error: {e}", e.lineno or 0, "")]

        visitor = CallVisitor()
        visitor.visit(tree)

        for func_name, lineno, node in visitor.calls:
            # Check 1: Exists
            if func_name not in self.api_spec.symbols:
                # We skip standard python builtins for safety.
                if __builtins__ and func_name in __builtins__ and not isinstance(__builtins__.get(func_name), type(None)):
                     continue
                suggestion = self._suggest_fix(func_name)
                errors.append(
                    ValidationError(
                        message=f"Unknown API call: {func_name}. This function may not exist or is hallucinated.",
                        line=lineno,
                        symbol=func_name,
                    )
                )
                if suggestion:
                    errors[-1].message += f" Did you mean '{suggestion}'?"
                    # Dynamic addition for the CLI representation
                    setattr(errors[-1], "suggestion", suggestion)
                continue

            # Check 2: Arguments matching (Critical Upgrade)
            arg_error = self._validate_args(func_name, node)
            if arg_error:
                errors.append(
                    ValidationError(
                        message=arg_error,
                        line=lineno,
                        symbol=func_name
                    )
                )

        return errors

    def _suggest_fix(self, func_name: str) -> str:
        """
        Simple similarity-based suggestion using basic inclusion checks.
        Could be upgraded to Levenshtein distance later.
        """
        for known in self.api_spec.symbols:
            # If the user typed `fake_relu`, maybe `relu` is known
            if func_name in known or known in func_name:
                return known
        return None

    def _validate_args(self, func_name: str, node: ast.Call) -> str:
        """
        Validates argument counts against the extracted signature.
        """
        expected_signature = self.api_spec.signatures.get(func_name)
        
        # Basic heuristic
        if expected_signature:
            # Clean up default generic/typing decorators which might skew comma counting
            clean_sig = expected_signature.split('->')[0]
            if '(' in clean_sig and ')' in clean_sig:
                args_str = clean_sig[clean_sig.find('(')+1:clean_sig.rfind(')')]
                if not args_str.strip() or args_str.strip() == 'self':
                    expected_args = 0
                else:
                    # Very Naive split: doesn't account for default kwargs, just raw theoretical maximums.
                    expected_args = args_str.count(",") + 1
                    # Subtract generic *args or **kwargs or basic `self` counts
                    if 'self' in args_str: expected_args -= 1
                    if '*' in args_str: expected_args = -1 # Accept infinite args if variadic

                actual_args = len(node.args) + len(node.keywords)
                
                # Check for strict mismatch (expected > actual without defaults is complex, so we do basic check)
                # This focuses on over-applying arguments or missing them entirely
                if expected_args != -1 and actual_args > expected_args:
                    return f"Argument mismatch in {func_name}: expected max {expected_args}, got {actual_args}"
                
        return None
