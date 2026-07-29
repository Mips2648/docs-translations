import os
from typing import overload


class InputsParser:
    @overload
    def read_str(self, name: str) -> str | None: ...
    @overload
    def read_str(self, name: str, default: str) -> str: ...

    def read_str(self, name: str, default: str | None = None) -> str | None:
        val = os.getenv(name, "").strip()
        return val if val != "" else default

    def read_bool(self, name: str) -> bool:
        val = self.read_str(name)
        true_values = ['true', 'True', 'TRUE']
        false_values = ['false', 'False', 'FALSE']
        if val in true_values:
            return True
        elif val in false_values:
            return False
        else:
            raise ValueError(f'Input does not meet specifications: {name}.\n Support boolean input list: "true | True | TRUE | false | False | FALSE"')

    def read_list(self, name: str, allowed_values: list) -> list[str]:
        val = self.read_str(name)
        if val is None:
            raise ValueError(f'Input does not meet specifications: {name}.\n {name} is required')
        values = [s.strip() for s in val.split(',')]
        for s in values:
            if s not in allowed_values:
                raise ValueError(f'Input does not meet specifications: {name}.\n {s} not in list: {allowed_values}')
        return values

    def read_one_of_str(self, name: str, allowed_values: list) -> str:
        val = self.read_str(name)
        if val is None or val not in allowed_values:
            raise ValueError(f'Input does not meet specifications: {name}.\n {val} not in list: {allowed_values}')
        return val
