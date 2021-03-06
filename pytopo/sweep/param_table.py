from typing import List
from qcodes import ParamSpec


class ParamTable:
    """
    A ParamTable is used by sweep objects to keep track of parameters and
    their inter dependencies.
    """
    def __init__(self, param_specs: List[ParamSpec],
                 nests: List[List[str]]=None) ->None:
        """
        Args:
            param_specs: A list of all parameter
                specification objects generated by the sweep object

            nests: A list of lists whereby the inner list is one of strings
                representing parameter names. Example:
                >>> nests = [['x', 'y', 'i'], ['x', 'j']]
                This means that parameter 'i' is dependent on 'x' and 'y'
                while parameter 'j' is dependent only on 'x'.
        """

        self._param_specs = param_specs
        # A list of lists. Inner list is a list of names
        self._nests = [[spec.name] for spec in
                       self._param_specs] if nests is None else nests

        self._dependencies_resolved = False

    def check_unresolved(self) ->None:
        """
        We cannot perform operations on tables with resolved dependencies,
        because operations alter these dependencies.
        """
        if self._dependencies_resolved:
            raise TypeError("Cannot operate on a parameter table with already "
                            "resolved dependencies")

    def copy(self) ->'ParamTable':
        """
        Return a copy of this table
        """
        return ParamTable(self.param_specs, self.nests)

    def nest(self, other: 'ParamTable') ->'ParamTable':
        """
        This operation is triggered when we nest sweep objects. If nests of
        self is [['x']] and that of other is [['i', 'j']], the resulting table
        will have nests equal to [['x', 'i'], ['x', 'j']]

        Args:
            other: A table to nest in self
        """
        self.check_unresolved()
        other.check_unresolved()

        param_specs = self.param_specs + other.param_specs
        nests = [self.nests[0] + nest for nest in other.nests]

        return ParamTable(param_specs, nests)

    def chain(self, other: 'ParamTable') ->'ParamTable':
        """
        This operation is triggered when we chain sweep objects.

        Args:
            other: A table to chain with self
        """
        self.check_unresolved()
        other.check_unresolved()

        param_specs = self.param_specs + other.param_specs
        nests = self.nests + other.nests

        return ParamTable(param_specs, nests)

    @property
    def param_specs(self) ->List[ParamSpec]:
        return [spec.copy() for spec in self._param_specs]

    @property
    def nests(self) ->List[List[str]]:
        return [list(nest) for nest in self._nests]

    def resolve_dependencies(self) ->None:
        """
        After creating sweep objects and param specs, resolve the dependencies.
        """
        if self._dependencies_resolved:
            return

        param_spec_dict = {spec.name: spec for spec in self._param_specs}

        for nest in self._nests:
            dependent_name = nest[-1]
            param_spec_dict[dependent_name].add_depends_on(nest[:-1])

        self._dependencies_resolved = True


def prod(param_tables: List[ParamTable]) ->ParamTable:
    """
    Created a parameter table by repeatedly nesting tables in a list.
    For example, prod([a, b, c]) will create a table from a.nest(b).nest(c)

    Args:
        param_tables
    """
    table_product = param_tables[0].copy()
    for table in param_tables[1:]:
        table_product = table_product.nest(table)

    return table_product


def add(param_tables: List[ParamTable]) ->ParamTable:
    """
    Created a parameter table by repeatedly chaining tables in a list.
    For example, add([a, b, c]) will create a table from a.chain(b).chain(c)

    Args:
        param_tables
    """
    table_product = param_tables[0].copy()
    for table in param_tables[1:]:
        table_product = table_product.chain(table)

    return table_product
