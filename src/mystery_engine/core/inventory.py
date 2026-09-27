from __future__ import annotations

from dataclasses import dataclass, field
from random import Random


@dataclass(frozen=True)
class ItemDefinition:
    id: str
    name: str
    description: str
    heal: int = 0
    throwable_damage: int = 0
    damage_type: str | None = None
    droppable: bool = True
    key_item: bool = False
    sfx_cue: str | None = None
    impact_sfx_cue: str | None = None
    projectile_key: str | None = None
    projectile_arc_px: float = 0.0


@dataclass
class InventoryStack:
    item: ItemDefinition
    quantity: int = 1


@dataclass
class Inventory:
    capacity: int
    stacks: list[InventoryStack] = field(default_factory=list)

    @property
    def occupied_slots(self) -> int:
        return len(self.stacks)

    def add(self, item: ItemDefinition, quantity: int = 1) -> bool:
        if quantity <= 0:
            return True
        existing = next((s for s in self.stacks if s.item.id == item.id), None)
        if existing:
            existing.quantity += quantity
            return True
        if self.occupied_slots >= self.capacity:
            return False
        self.stacks.append(InventoryStack(item, quantity))
        return True

    def remove(self, item_id: str, quantity: int = 1) -> bool:
        stack = next((s for s in self.stacks if s.item.id == item_id), None)
        if stack is None or stack.quantity < quantity:
            return False
        stack.quantity -= quantity
        if stack.quantity <= 0:
            self.stacks.remove(stack)
        return True

    def copy(self) -> "Inventory":
        return Inventory(self.capacity, [InventoryStack(s.item, s.quantity) for s in self.stacks])

    def apply_loss(self, rng: Random, per_item_loss_chance: float) -> list[str]:
        lost: list[str] = []
        for stack in list(self.stacks):
            if not stack.item.droppable or stack.item.key_item:
                continue
            kept = 0
            for _ in range(stack.quantity):
                if rng.random() < per_item_loss_chance:
                    lost.append(stack.item.name)
                else:
                    kept += 1
            stack.quantity = kept
            if stack.quantity == 0:
                self.stacks.remove(stack)
        return lost


@dataclass
class Wallet:
    carried: int = 0
    stored: int = 0

    def lose_carried_fraction(self, fraction: float) -> int:
        fraction = min(1.0, max(0.0, fraction))
        lost = int(self.carried * fraction)
        self.carried -= lost
        return lost
