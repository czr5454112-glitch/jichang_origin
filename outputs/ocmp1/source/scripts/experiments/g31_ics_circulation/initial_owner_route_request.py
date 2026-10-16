"""Callable native027 initial-A stage skeleton, not a campaign or certificate.

Construction admits the caller root before any capture/publication/fresh view.
The caller must use real complete native boundaries and the fixed participant
policy below. There is no command-line native runner in this preparation.
"""
from __future__ import annotations
import copy
import time
from types import FunctionType, SimpleNamespace
from . import initial_owner_route_contract as contract
from . import json_prediction_image as codec
from .initial_owner_route_client import InitialOwnerClient
from . import native_preexisting_v3_bound_adapter as adapter
from . import research_native_public_preference as public


def fixed_later(information, method):
    """Future code contract, not an optimization inferred from a peer ID."""
    if (adapter.is_native_collected(information)
            and information.get('status') == 'conditional_native_delivered_later_v3_model_input'):
        return {'status': 'predeclared_fixed_continuation',
                'selected_action': {'return_delay': 0., 'later_action': 'native_default'},
                'native_protection_certified': False, 'full_search_performed': False}
    return {'status': 'unknown_fixed_continuation_input', 'selected_action': None,
            'native_protection_certified': False}


def _fixed_decide():
    source = public.OwnerPolicy.decide_pending
    # Exact original method/closure. Only its method-selection provider is
    # private and fixed; original transport, collection, local checks, quiet
    # holds, reply/preflight and fallback code remain byte-for-byte executable.
    result = FunctionType(source.__code__, {**source.__globals__,
        'policy': SimpleNamespace(later=fixed_later)}, source.__name__, source.__defaults__, source.__closure__)
    result.__kwdefaults__ = copy.deepcopy(source.__kwdefaults__)
    return result


class FixedContinuationOwner(public.OwnerPolicy):
    decide_pending = _fixed_decide()


def native_boundary_complete(response, now):
    return (type(response) is dict and response.get('physical_time') == now
        and ((response.get('status') == 'reached' and response.get('horizon_complete') is True)
             or (response.get('status') in ('notified', 'horizon_reached')
                 and response.get('timestamp_complete') is True)))


def fixed_B_first_action(session, client, planning_id, *, native, accepted):
    """Independent fixed participant: reads B only, never sees A's choice."""
    if not adapter._valid_handle(native,session,accepted):
        raise ValueError('initial_stage:fixed_B_requires_live_accepted_session')
    information, ledger = adapter.collect_initial_ledger(native, session, 'B', planning_id, accepted=accepted)
    view = session.observe_protocol('B')
    rows = [t for t in view['trays'] if t['tray_id'] == 'E']
    request_id = None
    if (information.get('native_delivery_verified') is True and view['owner_id'] == 'B'
            and view['now'] == contract.START and len(rows) == 1):
        tray = rows[0]
        if (tray['node'] == 5 and tray['mode'] == 'empty' and tray['edge_to'] < 0
                and tray['available_at'] <= view['now']):
            client.activate('B', {'kind': 'predeclared_fixed_B_initial', 'at': view['now']})
            request_id = client.submit('B', 'transfer', 'fixed-initial-supply', tray_id='E', source=5,
                destination=1, earliest_departure=contract.START, expiry=39., message_delay=.01,
                causal={'relation':'predeclared_fixed_participant',
                        'participation_contract_sha256':contract.contract_sha256()})
    return {'owner':'B', 'information':information, 'view':view, 'request_id':request_id,
            'native_execution_certified':False}, ledger


class InitialOwnerRequest:
    """Single-use live stage. Pure supplied dictionaries cannot bind this class.

Warm admission includes initial collection on both predeclared participants.
Native construction, runtime acceptance, predictor startup and cleanup still
need separate full cold records in a future bounded campaign. They are never
amortized into this root. An outer caller must timestamp after final return.
"""
    def __init__(self, native, session, accepted, predictor, client, *, request_id):
        self.started_ns = time.perf_counter_ns()  # before checks, native reads or publication
        self.deadline_ns = self.started_ns + contract.BUDGET_NS
        self.cutoff_ns = self.deadline_ns - contract.FINALIZATION_RESERVE_NS
        if (type(request_id) is not str or not request_id or len(request_id) > 128
                or not adapter._valid_handle(native, session, accepted)
                or type(predictor) is not InitialOwnerClient or predictor.closed
                or predictor.ready.get('mode') != 'initial_A_two'
                or predictor.ready.get('proof',{}).get('participation_contract_sha256') != contract.contract_sha256()
                or type(client) is not public.LocalTransport or client.session is not session
                or client.rows or client.calls or session.physical_time != contract.ROOT_ADMISSION_PHYSICAL):
            raise ValueError('initial_stage:missing_fresh_live_session_or_process_authority')
        self.native, self.session, self.accepted = native, session, accepted
        self.predictor, self.client, self.request_id = predictor, client, request_id
        self.planning, self.channels = {}, {}
        self.information = self.ledger = self.reply = self.source = None
        self.choice = self.command_id = self.hop = None
        self.events = []
        self.state = 'admitted'
        self.last_boundary = None

    def _record(self, stage, value):
        self.events.append({'stage':stage, 'wall_ns':time.perf_counter_ns(),
                            'at':self.session.physical_time, 'value':copy.deepcopy(value)})

    def collect(self):
        if self.state != 'admitted':
            raise ValueError('initial_stage:collection_replay')
        # This host orchestration invokes each fixed participant's own native
        # capture. A later reads only its self-copy and delivered B message.
        for owner, peer in (('A','B'), ('B','A')):
            self.client.activate(owner, {'kind':'initial_A_root_collection', 'root_id':self.request_id})
            self.channels[owner] = self.client.submit(owner,'demand','seed-demand',target_owner=peer,
                message_delay=.01,publication_delay=.01)
            self.planning[owner] = self.client.submit(owner,'planning_snapshot','initial-planning',
                target_owner=peer,message_delay=.01,publication_delay=.01,expiry=.21)
        response = self.session.advance_to(contract.START, max_events=100000)
        self._record('collection_boundary', response)
        self.last_boundary = response
        if not native_boundary_complete(response, self.session.physical_time) or self.session.physical_time != contract.START:
            self.state = 'unknown_collection_boundary'
            return
        self.client.activate('A', {'kind':'initial_A_collected', 'root_id':self.request_id})
        self.client.refresh_owner('A', retry=False)
        self.information, self.ledger = adapter.collect_initial_ledger(self.native,self.session,'A',
            self.planning['A'],accepted=self.accepted)
        self._record('actual_A_collection', self.information)
        self.state = 'collected' if self.information.get('native_delivery_verified') is True else 'unknown_collection'

    def choose(self):
        if self.state != 'collected':
            raise ValueError('initial_stage:prediction_without_collection')
        packet = {'schema':contract.SCHEMA,'bundle':self.information['bundle'],
            'root_started_ns':self.started_ns,'decision_cutoff_ns':self.cutoff_ns,
            'root_deadline_ns':self.deadline_ns,'participation_contract_sha256':contract.contract_sha256()}
        self.reply = self.predictor.predict(self.request_id, packet)
        payload = self.reply['payload']
        if (payload['schema'] != contract.SCHEMA
                or payload['participation_contract_sha256'] != contract.contract_sha256()
                or payload['snapshot_sha256'] != codec.sha_bytes(codec.encode(packet['bundle']))
                or payload['budget']['root_started_ns'] != self.started_ns
                or payload['budget']['root_deadline_ns'] != self.deadline_ns
                or payload['budget']['decision_cutoff_ns'] != self.cutoff_ns
                or payload['native_authority'] is not False):
            raise ValueError('initial_stage:unbound_prediction_reply')
        self.choice = payload['selection']['choice']
        if self.choice not in (None,'native_default','prefer_2'):
            raise ValueError('initial_stage:undeclared_choice')
        # The worker's atomic call/codec can cross the allocated decision
        # boundary. A return after that boundary cannot authorize a preference.
        if self.choice == 'prefer_2' and time.perf_counter_ns() >= self.cutoff_ns:
            self.choice = 'native_default'
            self._record('decision_return_overrun_default_incumbent', {})
        self._record('two_choice_reply', self.reply)
        self.state = 'selected' if self.choice is not None else 'unknown_prediction'

    def final_revalidate_and_submit(self):
        if self.state != 'selected':
            raise ValueError('initial_stage:submission_without_selection')
        # Re-read the same source/delivered-pair interface and the current own
        # source/receiver. Never reuse a dictionary as fresh native authority.
        refreshed, _ = adapter.collect_initial_ledger(self.native,self.session,'A',self.planning['A'],accepted=self.accepted)
        view = self.session.observe_protocol('A')
        if (refreshed.get('native_delivery_verified') is not True
                or codec.encode(refreshed.get('bundle',{})) != codec.encode(self.information['bundle'])):
            self._record('final_changed_or_missing_capture_pair', refreshed)
            self.state = 'unknown_final_revalidation'
            return
        checked = contract.validate_final_local(view,self.information['bundle'],self.choice)
        self._record('final_local_and_receiver_check', {'view':view,'verdict':checked})
        if checked['status'] != 'fresh_local_precondition_checked':
            self.state = 'unknown_final_revalidation'
            return
        self.source = checked['source']
        if self.choice == 'prefer_2' and time.perf_counter_ns() >= self.deadline_ns:
            self.choice = 'native_default'
            self._record('pre_submit_root_overrun_default_incumbent', {})
        if self.choice == 'prefer_2':
            self.client.activate('A',{'kind':'initial_A_result','root_id':self.request_id})
            self.command_id = self.client.submit('A','route','initial-route',business_bag_id='loaded',tray_id='L',
                **{'from':0,'next':2},expected_generation=self.source['generation'],
                expected_traversal=self.source['traversal_id'],expiry=5.,message_delay=.01,
                causal={'relation':'result_handling','continuation_parent_roots':[self.request_id],
                        'predecessor_protocol_id':self.planning['A'],
                        'participation_contract_sha256':contract.contract_sha256()})
        self.state = 'pending_first_hop_and_ack'

    def observe_after_boundary(self, response):
        if self.state != 'pending_first_hop_and_ack':
            raise ValueError('initial_stage:unexpected_progress')
        now = self.session.physical_time
        if not native_boundary_complete(response,now):
            self._record('incomplete_native_boundary', response)
            return {'status':'open_incomplete_timestamp','closed':False}
        self.last_boundary = copy.deepcopy(response)
        self.client.activate('A', {'kind':'initial_A_continuation','root_id':self.request_id})
        self.client.refresh_owner('A')  # Immutable retries/actual delivered ACKs remain.
        view = self.session.observe_protocol('A')
        actual = contract.observed_first_hop(view,self.source)
        if self.hop is None and actual is not None:
            self.hop = actual
        command = self.session.protocol_command('A',self.command_id) if self.command_id else None
        self._record('continuation',{'view':view,'command_query_owner':'A',
            'command_query_id':self.command_id,'command':command,'hop':self.hop})
        # A retry may enqueue same-time native work after the incoming boundary.
        # Only an actual complete drain following these reads/refresh may close.
        verdict = contract.closure(self.choice,self.hop,command,queried_owner='A',request_id=self.command_id,now=now,timestamp_complete=False)
        return verdict

    def drain_and_finish_if_closed(self):
        if self.state != 'pending_first_hop_and_ack':
            raise ValueError('initial_stage:drain_without_active_request')
        now = self.session.physical_time
        drain = self.session.advance_to(now,max_events=100000)
        self._record('mandatory_drain',drain)
        if not native_boundary_complete(drain,self.session.physical_time) or self.session.physical_time != now:
            return {'status':'open_incomplete_timestamp','closed':False}
        # Queries after a complete drain do not submit or retry again.
        view = self.session.observe_protocol('A')
        actual = contract.observed_first_hop(view,self.source)
        if self.hop is None and actual is not None: self.hop = actual
        command = self.session.protocol_command('A',self.command_id) if self.command_id else None
        verdict = contract.closure(self.choice,self.hop,command,queried_owner='A',request_id=self.command_id,now=now,timestamp_complete=True)
        self._record('post_drain_observation',{'view':view,'command_query_owner':'A',
            'command_query_id':self.command_id,'command':command,'verdict':verdict})
        if verdict['closed']:
            self.state = verdict['status']
        return verdict

    def evidence(self):
        # Encoding is inside the request operation. An eventual native harness
        # must also record caller-outside-return/ledger tail and all cold work.
        result = {'schema':contract.SCHEMA,'root_id':self.request_id,'state':self.state,
            'owner':'A','root_started_ns':self.started_ns,'root_deadline_ns':self.deadline_ns,
            'decision_cutoff_ns':self.cutoff_ns,'choice':self.choice,'command_id':self.command_id,
            'hop':copy.deepcopy(self.hop),'events':copy.deepcopy(self.events),
            'participation_contract_sha256':contract.contract_sha256(),
            'complete_100ms_certified':False,'full_business_protection_certified':False,
            'scope':'First-hop request only; missing ACK remains open; no native experiment has been executed by this module.'}
        encoded = codec.artifact_encode(result)
        finished = time.perf_counter_ns()
        return {'evidence':result,'encoded':encoded,'body_finished_ns':finished,
                'body_elapsed_ns':finished-self.started_ns,'outside_return_tail_required':True}
