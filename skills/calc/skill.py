"""Calculation skill - fast eval with optional sympy for algebra"""
import re
import ast
import operator

_TRIGGERS = re.compile(
    r'(\d[\d\s\+\-\*\/\^\(\)\.]*[\d\)])'
    r'|calculate|solve|expand|factor',
    re.IGNORECASE
)

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

def _safe_eval_with_steps(node, steps=None):
    if steps is None:
        steps = []
    
    if isinstance(node, ast.Constant):
        return node.n
    elif isinstance(node, ast.BinOp):
        left_val = _safe_eval_with_steps(node.left, steps)
        right_val = _safe_eval_with_steps(node.right, steps)
        op_func = _OPS[type(node.op)]
        result = op_func(left_val, right_val)
        
        # Add intermediate step
        op_symbol = {
            ast.Add: '+', ast.Sub: '-', 
            ast.Mult: '*', ast.Div: '/', ast.Pow: '^'
        }.get(type(node.op), '?')
        
        left_str = _format_node(node.left)
        right_str = _format_node(node.right)
        steps.append(f"{left_str} {op_symbol} {right_str} = {result:g}")
        
        return result
    elif isinstance(node, ast.UnaryOp):
        operand_val = _safe_eval_with_steps(node.operand, steps)
        op_func = _OPS[type(node.op)]
        result = op_func(operand_val)
        
        # Add intermediate step for unary operations
        if isinstance(node.op, ast.USub):
            operand_str = _format_node(node.operand)
            steps.append(f"-{operand_str} = {result:g}")
        
        return result
    raise ValueError(f"unsupported: {node}")

def _format_node(node):
    if isinstance(node, ast.Constant):
        return f"{node.n:g}"
    elif isinstance(node, ast.BinOp):
        left_str = _format_node(node.left)
        right_str = _format_node(node.right)
        op_symbol = {
            ast.Add: '+', ast.Sub: '-', 
            ast.Mult: '*', ast.Div: '/', ast.Pow: '^'
        }.get(type(node.op), '?')
        return f"({left_str} {op_symbol} {right_str})"
    elif isinstance(node, ast.UnaryOp):
        operand_str = _format_node(node.operand)
        if isinstance(node.op, ast.USub):
            return f"-{operand_str}"
        return operand_str
    return str(node)

def _safe_eval(node):
    return _safe_eval_with_steps(node)[0]

def match(text):
    return bool(_TRIGGERS.search(text))

def respond(text):
    text = text.strip()
    steps = []

    # expand / factor / solve → sympyへ
    for cmd in ('expand', 'factor', 'solve'):
        m = re.search(rf'{cmd}\s*[:\s]\s*(.+)', text, re.IGNORECASE)
        if m:
            try:
                import sympy as sp
                expr_str = m.group(1).strip()
                x = sp.Symbol('x')
                expr = sp.sympify(expr_str)
                steps.append(f"Expression: {expr_str}")
                if cmd == 'expand':
                    steps.append(f"Expanded: {sp.expand(expr)}")
                elif cmd == 'factor':
                    steps.append(f"Factorized: {sp.factor(expr)}")
                elif cmd == 'solve':
                    steps.append(f"Solutions: x = {sp.solve(expr, x)}")
                return "\n".join(steps)
            except Exception as e:
                return f"{cmd} failed: {e}"

    # 数値計算 (astベース、高速)
    num_match = re.search(r'[\d\+\-\*\/\^\(\)\. ]+', text)
    if num_match:
        expr_str = num_match.group(0).strip()
        expr_safe = expr_str.replace('^', '**')
        try:
            tree = ast.parse(expr_safe, mode='eval')
            calculation_steps = []
            result = _safe_eval_with_steps(tree.body, calculation_steps)
            
            steps.append(f"Expression: {expr_str}")
            if calculation_steps:
                steps.append("Steps:")
                for step in calculation_steps:
                    steps.append(f"  {step}")
            steps.append(f"Result: {result:g}")
            return "\n".join(steps)
        except Exception as e:
            return f"Calculation failed: {e}"

    return "Examples: 3 + 4 * 2  /  expand: (x+1)^2  /  solve: x^2 - 4"
