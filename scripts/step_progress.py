"""In-memory checkpoints for one interrupted workflow step."""
from __future__ import annotations


class StepProgress:
    def __init__(self, control):
        self.control = control
        self.step = ""
        self.completed = {}

    def enter(self, step):
        if step != self.step:
            self.step = step
            self.completed.clear()

    def reset(self):
        self.step = ""
        self.completed.clear()

    def run(self, name, operation):
        """Keep successful results even if the runner is stopped before delivery."""
        self.control.check()
        if name not in self.completed:
            result = operation()
            if result is False:
                return result
            self.completed[name] = result
        return self.completed[name]

    def keys(self, name, keyboard, sequence):
        for index, (key, repeat) in enumerate(sequence):
            for number in range(repeat):
                self.run((name, index, number), lambda: keyboard.press(key))
                self.control.wait(0.25)
