from __future__ import annotations

from typing import Any


SUPPORTED_CONTAINER_TYPES = {2, 9, 10, 12, 14, 17}


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_container_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("A Components V2 payload object is required.")
    if payload.get("flags") != 32768:
        raise ValueError("A Components V2 payload with Discord flags is required.")

    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("A Components V2 payload with components is required.")

    def validate_component(component: Any, *, allow_container_children: bool = True) -> dict[str, Any]:
        if not isinstance(component, dict):
            raise ValueError("Each component must be an object.")

        component_type = component.get("type")
        if component_type not in SUPPORTED_CONTAINER_TYPES:
            raise ValueError("Unsupported container component type.")

        if component_type == 10:
            content = component.get("content")
            if not _is_non_empty_text(content):
                raise ValueError("TextDisplay components require content.")
            return {**component, "type": 10, "content": str(content).strip()}

        if component_type == 9:
            text = component.get("text")
            if not _is_non_empty_text(text):
                raise ValueError("Section components require text.")
            accessory = component.get("accessory")
            if accessory is not None and not isinstance(accessory, dict):
                raise ValueError("Section accessories must be objects.")
            return {**component, "type": 9, "text": str(text).strip()}

        if component_type == 12:
            items = component.get("items")
            if not isinstance(items, list) or not items:
                raise ValueError("MediaGallery components require at least one item.")
            normalized_items = []
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("MediaGallery items must be objects.")
                media = item.get("media") or {}
                if not isinstance(media, dict) or not _is_non_empty_text(media.get("url")):
                    raise ValueError("MediaGallery items require image URLs.")
                normalized_items.append({"media": {"url": str(media["url"]).strip()}})
            return {**component, "type": 12, "items": normalized_items}

        if component_type == 14:
            return {**component, "type": 14}

        if component_type == 2:
            label = component.get("label")
            style = component.get("style")
            action = component.get("action")
            if not _is_non_empty_text(label):
                raise ValueError("Button components require a label.")
            if style not in {1, 2, 3, 4, 5}:
                style = 1
            if action not in {"url", "custom_id"}:
                action = "url"
            return {
                **component,
                "type": 2,
                "label": str(label).strip(),
                "style": style,
                "action": action,
                "url": str(component.get("url") or "").strip() if action == "url" else None,
                "custom_id": str(component.get("custom_id") or "").strip() if action == "custom_id" else None,
            }

        if component_type == 17:
            children = component.get("components")
            if not isinstance(children, list) or not children:
                raise ValueError("Container components require at least one child component.")
            if not any(isinstance(child, dict) and child.get("type") == 10 for child in children):
                raise ValueError("Container components require at least one TextDisplay child.")
            normalized_children = [validate_component(child, allow_container_children=True) for child in children]
            return {**component, "type": 17, "components": normalized_children}

        raise ValueError("Unsupported container component.")

    normalized_components = [validate_component(component) for component in components]
    return {"flags": 32768, "components": normalized_components}
