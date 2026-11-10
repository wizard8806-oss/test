#!/usr/bin/env python3
"""Reviewed SK-070HE page-sized storage outside the scene stream.

Native 7.1 fourteen/sixteen-page samples show section1 has one byte per
page; section21 has an unchanged 48-byte prefix and four bytes per page.
Their precise UI meaning is not asserted. Adding scenes also requires
extending both arrays; a valid prefix/directory alone cannot prove this.
"""
from repair_skm_section_index import read_directory
from skm_project_header import read_project_header


def read_page_storage(raw,require_consistent=True):
    header=read_project_header(raw);directory=read_directory(raw)
    if header['model']!='SK-070HE':raise ValueError('Page storage reviewed only for SK-070HE')
    entries=directory['entries'];flag_start,flag_end=entries[1:3]
    word_start,word_end=entries[21:23]
    if word_end-word_start<48 or (word_end-word_start-48)%4:
        raise ValueError('Unreviewed page-word section shape')
    counts=(flag_end-flag_start,(word_end-word_start-48)//4)
    if require_consistent and counts!=(header['pageCount'],)*2:
        raise ValueError('Page count %d differs from section1/21 arrays %s'%(header['pageCount'],counts))
    return dict(pageCount=header['pageCount'],flagEntries=counts[0],wordEntries=counts[1],
        flagStart=flag_start,flagEnd=flag_end,wordStart=word_start,wordEnd=word_end,wordPrefixBytes=48)


def page_storage_extensions(raw,target_count):
    current=read_page_storage(raw,require_consistent=False)
    count=current['flagEntries']
    if (current['wordEntries']!=count or current['pageCount'] not in (count,target_count)
            or not isinstance(target_count,int) or not 1<=count<=target_count<=1000):
        raise ValueError('Unreviewed page array extension')
    extra=target_count-count
    if not extra:return []
    return [(current['flagEnd'],b'',b'\0'*extra,'page flag entries section1'),
            (current['wordEnd'],b'',b'\0'*(4*extra),'page word entries section21')]
