"""Selector definitions and helper utilities for parsing service-public.bj."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServicePublicSelectors:
    """CSS selectors used to extract information from service-public.bj."""

    category_list: str = "ul.sp-theme-list li"
    category_link: str = "a.fr-footer__top-link"

    search_result: str = "li[id^='result_']"
    search_link: str = "a.fr-link"
    search_title: str = "a.fr-link span span"
    search_description: str = ".sp-description, .description"

    detail_title: str = "h1#titlePage, h1.fr-h1"
    detail_intro: str = "div#intro p, p.fr-text--lg"
    detail_last_updated: str = "time[datetime]"
    detail_sections: str = "section.fr-accordion[data-test='div-chapter']"
    detail_section_title: str = ".sp-accordion-chapter-btn-text"
    detail_section_content: str = (
        "div.sp-chapter-content p[data-test='contenu-texte'], "
        "div.sp-chapter-content ul.sp-item-list li, "
        "div.sp-chapter-content div.fr-highlight p"
    )

    document_link: str = "a.fr-link, a.fr-download__link"


SERVICE_PUBLIC_SELECTORS = ServicePublicSelectors()


def normalise_whitespace(value: str) -> str:
    """Collapse multiple whitespace characters into a single space."""

    return " ".join(value.split())
