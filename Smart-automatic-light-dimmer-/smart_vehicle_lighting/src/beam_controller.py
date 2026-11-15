"""
Beam Control State Machine Module
Implements formal state machine:
- NORMAL_BEAM
- LOW_BEAM
- UNCERTAIN

Decision Logic:
1. When ambient conditions are dark and no confirmed glare-producing oncoming vehicle is detected: NORMAL_BEAM
2. When approaching headlights confirmed with sufficient persistence: LOW_BEAM
3. Cooldown / hysteresis before returning to NORMAL_BEAM
4. If conditions are UNCERTAIN (e.g. sensor conflict, flickering, excessive glare): Select conservative LOW_BEAM to prevent blinding oncoming drivers
5. Safe fallback on camera or serial disconnection
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class BeamState(Enum):
    NORMAL_BEAM = "NORMAL_BEAM"
    LOW_BEAM = "LOW_BEAM"
    UNCERTAIN = "UNCERTAIN"

@dataclass
class BeamDecision:
    state: BeamState
    hardware_command: str  # "NORMAL" or "LOW"
    reason: str
    confidence: float
    time_in_state: float
    is_state_transition: bool

class BeamController:
    def __init__(self, config: dict):
        self.cfg = config.get("sensor_fusion", {})
        self.conservative_fallback = self.cfg.get("conservative_fallback_beam", "LOW")
        
        # State machine tracking
        self.current_state = BeamState.NORMAL_BEAM
        self.last_transition_time = time.time()
        self.state_enter_time = time.time()
        
        # Minimum time to remain in a state to eliminate rapid relay chatter (chatter prevention)
        self.min_state_duration_sec = 1.0

    def evaluate(
        self,
        headlight_confirmed: bool,
        headlight_confidence: float,
        ambient_dark: bool,
        is_stream_healthy: bool,
        uncertainty_flag: bool = False,
        detail_reason: str = "",
        emergency_obstacle: bool = False
    ) -> BeamDecision:
        """
        Evaluates current fused inputs and transitions state machine.
        Returns BeamDecision with commanded state and explanation.
        """
        now = time.time()
        time_in_current_state = now - self.state_enter_time
        prev_state = self.current_state
        target_state = self.current_state
        decision_reason = ""
        decision_conf = headlight_confidence

        # 1. Safety Fallback: Camera stream failure
        if not is_stream_healthy:
            target_state = BeamState.UNCERTAIN if self.conservative_fallback == "LOW" else BeamState.NORMAL_BEAM
            decision_reason = "Safety Fallback: Camera stream unavailable; applying conservative low beam"
            decision_conf = 0.0

        # 2. Ambient Daylight Check
        elif not ambient_dark:
            # During bright daylight, high beam is disabled
            target_state = BeamState.LOW_BEAM
            decision_reason = "Daytime detected by LDR: High beam disabled"
            decision_conf = 1.0

        # 3. Emergency / Close Condition (if flagged)
        elif emergency_obstacle:
            target_state = BeamState.LOW_BEAM
            decision_reason = "Close proximity obstacle flagged: Glare prevention low beam"
            decision_conf = 0.95

        # 4. Uncertainty Flag
        elif uncertainty_flag:
            target_state = BeamState.UNCERTAIN
            decision_reason = f"Uncertain lighting condition: {detail_reason}"
            decision_conf = 0.50

        # 5. Oncoming Headlights Detected
        elif headlight_confirmed:
            target_state = BeamState.LOW_BEAM
            decision_reason = f"Glare Prevention: Oncoming vehicle headlights confirmed ({detail_reason})"
            decision_conf = max(headlight_confidence, 0.75)

        # 6. Clear Nighttime Road Ahead
        else:
            target_state = BeamState.NORMAL_BEAM
            decision_reason = f"Clear road visibility: Normal/High beam active ({detail_reason})"
            decision_conf = 1.0 - headlight_confidence

        # Hysteresis:
        # 1. Switching to LOW_BEAM or UNCERTAIN (safety / anti-glare): IMMEDIATE!
        # 2. Returning to NORMAL_BEAM: enforce min_state_duration_sec to prevent relay chatter
        is_transition = False
        if target_state != self.current_state:
            can_switch = False
            if target_state in [BeamState.LOW_BEAM, BeamState.UNCERTAIN]:
                # Safety action: dim headlights immediately
                can_switch = True
            elif time_in_current_state >= self.min_state_duration_sec:
                # Returning to normal beam: enforce hold time
                can_switch = True

            if can_switch:
                self.current_state = target_state
                self.state_enter_time = now
                self.last_transition_time = now
                is_transition = True
                logger.info(f"Beam state changed: {prev_state.value} -> {self.current_state.value} | Reason: {decision_reason}")
            else:
                decision_reason = f"Hold state (anti-chatter: {self.min_state_duration_sec - time_in_current_state:.1f}s) - {decision_reason}"

        # Resolve hardware relay command
        # Conservative policy: UNCERTAIN maps to LOW beam to protect human oncoming drivers
        if self.current_state == BeamState.LOW_BEAM:
            hw_cmd = "LOW"
        elif self.current_state == BeamState.UNCERTAIN:
            hw_cmd = "LOW" if self.conservative_fallback == "LOW" else "NORMAL"
        else:
            hw_cmd = "NORMAL"

        return BeamDecision(
            state=self.current_state,
            hardware_command=hw_cmd,
            reason=decision_reason,
            confidence=float(decision_conf),
            time_in_state=time_in_current_state,
            is_state_transition=is_transition
        )
