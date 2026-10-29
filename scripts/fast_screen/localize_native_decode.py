"""Keep valid article decisions when another returned article is malformed."""
def decode_articles(packet,response,strict_decode):
    if 'expected_candidate_ids'in packet:return strict_decode(packet,response),[]
    if not isinstance(response,dict)or set(response)!={'items'}or not isinstance(response['items'],list):raise ValueError('Invalid compact root')
    allowed={r['id']for r in packet['articles']};seen=set();items=[];issues=[]
    for item in response['items']:
        id=item.get('i')if isinstance(item,dict)else None
        if id not in allowed or id in seen:raise ValueError('Unknown or duplicate article ID')
        seen.add(id)
        try:items.extend(strict_decode(packet,{'items':[item]})['items'])
        except (ValueError,KeyError,TypeError)as e:
            # Internal invalid code is deliberately rejected by canonical
            # intake. No invalid semantic value becomes accepted or excluded.
            items.append({'id':id,'code':'invalid_compact_article','views':[]})
            issues.append({'id':id,'error':str(e),'disposition':'unread_requires_local_completion'})
    return {'items':items},issues
