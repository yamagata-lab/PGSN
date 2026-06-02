# pgsn_cli.py
import click
import importlib.util
import sys
from pathlib import Path

default_layout = {
    "rankdir": "TB",
    "splines": "spline",
    "nodesep": "0.6",
    "ranksep": "1.2",
}

try:
    from pgsn import dsl
    from pgsn import gsn
    from pgsn import pgsn_xml
    from pgsn.pgsn_term import Term
except ImportError as e:
    print(f"Error: Could not import PGSN modules: {e}")
    print("Please ensure gsn.py, dsl.py, pgsn_term.py, and pgsn_xml.py are accessible.")
    sys.exit(1)


def load_term_from_py_file(file_path: str, term_name: str) -> Term:
    """Load a named Term object from a trusted Python (.py) file."""
    path = Path(file_path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None:
        raise ImportError(f"Could not create a module spec from '{path}'.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    term_object = getattr(module, term_name, None)
    if term_object is None:
        raise AttributeError(f"Object '{term_name}' not found in module '{spec.name}'.")

    return term_object


def load_term(input_file: str, term_name: str) -> Term:
    """
    Load a Term from a .py, .json, or .xml file without evaluating it.
    Evaluation (fully_eval) is the caller's responsibility.
    """
    if input_file.endswith('.py'):
        return load_term_from_py_file(input_file, term_name)
    elif input_file.endswith('.json'):
        with open(input_file, 'r', encoding='utf-8') as f:
            return dsl.json_loads(f.read())
    elif input_file.endswith('.xml'):
        return pgsn_xml.compile_pgsn(input_file)
    else:
        raise ValueError(
            f"Unsupported file type for '{input_file}'. Use .py, .json, or .xml."
        )


# ===============================================================
# The Command-Line Interface
# ===============================================================

@click.group()
def cli():
    """A command-line tool for Programmable GSN (PGSN)."""
    pass


@cli.command()
@click.argument('input_file', type=click.Path(exists=True, dir_okay=False))
@click.option('--term-name', default='main', help='The name of the Term object to evaluate.')
@click.option('--doc-type', '-d', default='plain', type=click.Choice(['plain', 'json']),
              help='The output document format.')
@click.option('--output', '-o', default=None, help='The output filename.')
@click.option('--steps', '-s', help='maximum number of evaluation steps', type=int, default=1000000)
def doc(input_file, term_name, doc_type, output, steps):
    """Evaluates a PGSN term and outputs a document in a specified format."""

    click.echo(f"Generating '{output}' from '{input_file}'", err=True)

    try:
        term = load_term(input_file, term_name)
        click.echo(f"Evaluating term '{term_name}'...", err=True)
        evaluated_gsn = term.fully_eval(steps=steps)

        tree = gsn.gsn_tree(evaluated_gsn)

        if doc_type == 'plain':
            document = tree.show(stdout=False)
        elif doc_type == 'json':
            document = tree.to_json()
        else:
            click.echo("Error: Unsupported document type. Use plain or json.", err=True)
            return

        if output and output != '-':
            with open(output, 'w', encoding='utf-8') as f:
                f.write(document)
        else:
            click.echo(document)

        click.echo("Done.", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.argument('input_file', type=click.Path(exists=True, dir_okay=False))
@click.option('--term-name', default='main', help='The name of the Term object to evaluate.')
@click.option('--output', '-o', default=None, help='The output filename (without extension).')
@click.option('--format', '-f', 'image_format', type=click.Choice(['svg', 'png', 'pdf']), default='svg',
              help='The output image format.')
@click.option('--steps', '-s', help='maximum number of evaluation steps', type=int, default=1000000)
def render(input_file, term_name, output, image_format, steps):
    """Evaluates a PGSN term and renders it as a graph."""

    click.echo(f"Processing '{input_file}' to render a graph...", err=True)

    try:
        term = load_term(input_file, term_name)
        click.echo(f"Evaluating term '{term_name}'...", err=True)
        evaluated_gsn = term.fully_eval(steps=steps)

        dot = gsn.gsn_dot(evaluated_gsn)

        if output and output != '-':
            click.echo(f"Saving graph to '{output}.{image_format}'...", err=True)
            dot.render(filename=output, view=False, format=image_format, cleanup=True)
        elif output == '-':
            # Explicit stdout
            click.echo(dot.pipe(format=image_format))
        else:
            # No output specified: view if interactive, else pipe to stdout
            if sys.stdout.isatty():
                dot.view(cleanup=True)
            else:
                click.echo(dot.pipe(format=image_format))

        click.echo("Done.", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.argument('input_file', type=click.Path(exists=True, dir_okay=False))
@click.option('--term-name', default='main', help='The name of the Term object to compile.')
@click.option('--output', '-o', default=None, help='The output JSON filename.')
def compile(input_file, term_name, output):
    """Compiles a trusted PGSN (.py or .xml) file into a secure JSON format."""
    click.echo(f"Compiling '{input_file}' to JSON...", err=True)

    try:
        term = load_term(input_file, term_name)
        json_str = dsl.json_dumps(term, indent=None, separators=(',', ':'))

        if output and output != '-':
            click.echo(f"Saving JSON to '{output}'...", err=True)
            with open(output, 'w', encoding='utf-8') as f:
                f.write(json_str)
        else:
            click.echo(json_str)

        click.echo("Done.", err=True)

    except Exception as e:
        click.echo(f"Error: {e}", err=True)


if __name__ == '__main__':
    cli()