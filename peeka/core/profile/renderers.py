# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportImplicitOverride=false, reportUnusedCallResult=false, reportUnnecessaryComparison=false, reportUnannotatedClassAttribute=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
"""Profile renderer contracts and concrete renderers."""

import json
from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple
from typing import TextIO

from peeka.core.profile.models import ProfileSession
from peeka.core.profile.models import SampleRecord
from peeka.core.profile.processors import ProcessedProfile


class ProfileRenderer(ABC):
    """Contract for rendering processed profile data to a text stream."""

    @abstractmethod
    def render(self, processed: "ProcessedProfile", output: TextIO) -> None:
        """Render a processed profile into the provided text output stream."""


class JsonRenderer(ProfileRenderer):
    """Render processed profiles as JSON."""

    def __init__(self, pretty: bool = False, include_samples: bool = False) -> None:
        self._pretty = pretty
        self._include_samples = include_samples

    def render(self, processed: "ProcessedProfile", output: TextIO) -> None:
        payload: Dict[str, Any] = {
            "profile_id": processed.profile_id,
            "backend": processed.backend,
            "started_at": processed.session.started_at,
            "summary": processed.session.summary.to_dict()
            if processed.session.summary is not None
            else None,
            "top_list": processed.top_list,
        }
        if self._include_samples:
            payload["samples"] = [sample.to_dict() for sample in processed.session.samples]

        json.dump(
            payload,
            output,
            ensure_ascii=False,
            indent=2 if self._pretty else None,
            sort_keys=self._pretty,
        )


class TextRenderer(ProfileRenderer):
    """Render processed profiles as plain text."""

    def render(self, processed: "ProcessedProfile", output: TextIO) -> None:
        session = processed.session
        summary = session.summary
        duration_ms = self._get_duration_ms(session)
        sample_count = summary.sample_count if summary is not None else len(session.samples)

        output.write(f"Profile: {processed.profile_id}\n")
        output.write(f"Backend: {processed.backend}\n")
        output.write(f"Duration: {duration_ms:.2f} ms\n")
        output.write(f"Samples: {sample_count}\n")
        output.write("\n")
        output.write(self._render_table(processed.top_list))

    def _get_duration_ms(self, session: ProfileSession) -> float:
        summary = session.summary
        if summary is not None:
            return float(summary.duration_ms)
        if session.ended_at is not None:
            return max((session.ended_at - session.started_at) * 1000.0, 0.0)
        return 0.0

    def _render_table(self, top_list: List[Dict[str, Any]]) -> str:
        headers = ["function", "own%", "total%", "own_count", "total_count"]
        rows: List[List[str]] = []

        for item in top_list:
            name = str(item.get("name", ""))
            filename = item.get("filename")
            line = item.get("lineno") or item.get("line")
            if filename is not None and line is not None:
                name = f"{name} ({filename}:{line})"
            rows.append([
                name,
                f"{float(item.get('own_pct', 0.0)):.2f}%",
                f"{float(item.get('total_pct', 0.0)):.2f}%",
                str(item.get("own_count", 0)),
                str(item.get("total_count", 0)),
            ])

        widths = [len(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(cell))

        lines = [self._format_row(headers, widths), self._format_separator(widths)]
        lines.extend(self._format_row(row, widths) for row in rows)
        return "\n".join(lines) + "\n"

    def _format_row(self, row: List[str], widths: List[int]) -> str:
        cells = []
        for index, cell in enumerate(row):
            if index == 0:
                cells.append(cell.ljust(widths[index]))
            else:
                cells.append(cell.rjust(widths[index]))
        return "  ".join(cells)

    def _format_separator(self, widths: List[int]) -> str:
        return "  ".join("-" * width for width in widths)


class SpeedscopeRenderer(ProfileRenderer):
    """Render processed profiles as a speedscope sampled profile."""

    def render(self, processed: "ProcessedProfile", output: TextIO) -> None:
        session = processed.session
        frame_lookup: Dict[Tuple[Any, Any, Any, Any], int] = {}
        frames: List[Dict[str, Any]] = []
        profiles: List[Dict[str, Any]] = []

        sample_groups = self._group_samples_by_thread(session.samples)
        multi_thread = len(sample_groups) > 1
        if not sample_groups:
            sample_groups = [[]]
        for samples in sample_groups:
            stacks: List[List[int]] = []
            weights: List[float] = []
            for index, sample in enumerate(samples):
                stacks.append(self._stack_indices(sample, frame_lookup, frames))
                weights.append(self._sample_weight_ms(session, samples, index))

            profiles.append({
                "type": "sampled",
                "name": self._profile_name(processed.profile_id, samples, multi_thread),
                "unit": "milliseconds",
                "startValue": 0,
                "endValue": sum(weights),
                "samples": stacks,
                "weights": weights,
            })

        payload: Dict[str, Any] = {
            "$schema": "https://www.speedscope.app/file-format-schema.json",
            "shared": {"frames": frames},
            "profiles": profiles,
            "activeProfileIndex": 0,
            "name": processed.profile_id,
            "exporter": "peeka",
        }

        json.dump(payload, output, ensure_ascii=False)

    def _group_samples_by_thread(
        self,
        samples: List[SampleRecord],
    ) -> List[List[SampleRecord]]:
        sample_groups: Dict[int, List[SampleRecord]] = {}
        thread_order: List[int] = []
        for sample in samples:
            if sample.thread_id not in sample_groups:
                sample_groups[sample.thread_id] = []
                thread_order.append(sample.thread_id)
            sample_groups[sample.thread_id].append(sample)
        return [sample_groups[thread_id] for thread_id in thread_order]

    def _stack_indices(
        self,
        sample: SampleRecord,
        frame_lookup: Dict[Tuple[Any, Any, Any, Any], int],
        frames: List[Dict[str, Any]],
    ) -> List[int]:
        stack_indices: List[int] = []
        for frame in sample.stack:
            key = (frame.name, frame.module, frame.filename, frame.lineno)
            frame_index = frame_lookup.get(key)
            if frame_index is None:
                frame_index = len(frames)
                frame_lookup[key] = frame_index
                frame_data: Dict[str, Any] = {"name": frame.name}
                if frame.filename:
                    frame_data["file"] = frame.filename
                if frame.lineno is not None:
                    frame_data["line"] = frame.lineno
                if frame.module is not None:
                    frame_data["module"] = frame.module
                frames.append(frame_data)
            stack_indices.append(frame_index)
        return stack_indices

    def _profile_name(
        self,
        profile_id: str,
        samples: List[SampleRecord],
        multi_thread: bool,
    ) -> str:
        if not multi_thread or not samples:
            return profile_id
        sample = samples[0]
        thread_label = sample.thread_name or str(sample.thread_id)
        return f"{profile_id} [{thread_label}]"

    def _sample_weight_ms(
        self,
        session: ProfileSession,
        samples: List[SampleRecord],
        index: int,
    ) -> float:
        sample = samples[index]
        if index + 1 < len(samples):
            next_sample = samples[index + 1]
            return max((next_sample.timestamp - sample.timestamp) * 1000.0, 0.0)
        interval_ms = getattr(session.config, "interval_ms", 0)
        return float(interval_ms)


class TimelineRenderer(ProfileRenderer):
    """Render timeline data as Chrome trace events by reusing PerfettoRenderer."""

    def render(self, processed: "ProcessedProfile", output: TextIO) -> None:
        if processed.timeline is None:
            from peeka.core.profile.processors import BuildTimelineProcessor
            temp_processed = BuildTimelineProcessor().process(processed.session)
            processed.timeline = temp_processed.timeline

        PerfettoRenderer().render(processed, output)


class PerfettoRenderer(ProfileRenderer):
    """Render processed profiles as Chrome trace events for Perfetto."""

    def render(self, processed: "ProcessedProfile", output: TextIO) -> None:
        trace_events: List[Dict[str, Any]] = []
        for sample in processed.session.samples:
            top_name = sample.stack[-1].name if sample.stack else "<empty>"
            trace_events.append(
                {
                    "name": top_name,
                    "ph": "i",
                    "ts": sample.timestamp * 1000000.0,
                    "tid": sample.thread_id,
                    "pid": 0,
                    "s": "t",
                }
            )

        json.dump({"traceEvents": trace_events}, output, ensure_ascii=False)
