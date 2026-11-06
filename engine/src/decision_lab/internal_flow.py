"""Opt-in, loopback-only developer view of the latest navigation snapshot.

This is UI-reported navigation, not trusted simulation evidence or analytics.
The browser omits typed text and sends bounded navigation labels only. Extra
world-state or model-payload fields are rejected; this is not a trusted client.
"""
from copy import deepcopy
from threading import RLock


class InternalFlow:
    def __init__(self):
        self._lock=RLock();self._revision=0;self._value=None
    def update(self,value):
        if type(value)is not dict or set(value)!={'phase','current','actor_route','steps'}:raise ValueError('exact internal navigation snapshot required')
        for key in ('phase','current','actor_route'):
            if type(value[key])is not str or len(value[key])>100 or any(ord(c)<32 for c in value[key]):raise ValueError('bounded navigation label required')
        if type(value['steps'])is not list or len(value['steps'])>120:raise ValueError('bounded navigation steps required')
        ids=set()
        for step in value['steps']:
            if type(step)is not dict or set(step)!={'id','label','input','answer','visited'}:raise ValueError('exact step required')
            for key in ('id','label','input','answer'):
                if type(step[key])is not str or len(step[key])>(200 if key in ('label','answer')else 100)or any(ord(c)<32 for c in step[key]):raise ValueError('bounded plain step label required')
            if type(step['visited'])is not bool or step['id']in ids:raise ValueError('unique navigation step required')
            ids.add(step['id'])
        with self._lock:self._value=deepcopy(value);self._revision+=1;return {'accepted':True,'revision':self._revision}
    def snapshot(self):
        with self._lock:return {'schema_version':'internal-question-flow.v1','revision':self._revision,'navigation':deepcopy(self._value),'source':'Latest opt-in local browser snapshot; not execution evidence.'}
