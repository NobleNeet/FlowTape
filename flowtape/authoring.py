"""Logical target references for explicit binding workflows."""


def referenced_targets(document):
    result=set()
    def condition(value):
        op, data=next(iter(value.items()))
        if op in {'all','any'}:
            for child in data: condition(child)
        elif op=='not': condition(data)
        elif op in {'exists','not_exists','visible','hidden','enabled','disabled'}: result.add(data)
        elif op in {'text_equals','value_equals'}: result.add(data['target'])
    def walk(steps):
        for node in steps:
            if 'action' in node:
                if node['action']!='switch_window':
                    for field in ('target','from','to'):
                        if field in node: result.add(node[field])
                if node['action'] in {'wait','check'}:
                    value=node.get('until',node.get('condition'))
                    if 'download_complete' not in value: condition(value)
            elif 'if' in node:
                condition(node['if']);walk(node['then']);walk(node.get('else',[]))
            else:
                kind=next(key for key in ('repeat','while','for_each') if key in node)
                if kind=='while': condition({key:value for key,value in node[kind].items() if key not in {'steps','timeout','max_iterations'}})
                walk(node[kind]['steps'])
    walk(document['steps'])
    return result
