"""
Watch Command - Monitor function calls and return values
Similar to Arthas 'watch' command
"""

import time
from typing import Dict, Any, Optional

from peeka.utils.formatters import format_value
from ..commands.base import BaseCommand


class WatchCommand(BaseCommand):
    """
    Watch command - monitors function execution
    
    Usage:
        watch <module.class.method> [-x depth] [-n times]
    
    Examples:
        watch mymodule.MyClass.my_method
        watch mymodule.my_function -x 2 -n 5
    """

    def __init__(self):
        super().__init__()
        self.watches = {}

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute watch command
        
        Args:
            params: {
                'pattern': 'module.class.method',  # What to watch
                'depth': 2,                         # Output depth
                'times': -1,                        # Number of times (-1 = infinite)
                'action': 'start' | 'stop' | 'status'
            }
        
        Returns:
            Result dictionary with status and data
        """
        try:
            action = params.get('action', 'start')

            if action == 'start':
                return self._start_watch(params)
            elif action == 'stop':
                return self._stop_watch(params)
            elif action == 'status':
                return self._get_status(params)
            else:
                return {
                    'status': 'error',
                    'error': f'Unknown action: {action}'
                }

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }

    def _start_watch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start watching a function"""
        self.validate_params(params, ['pattern'])

        pattern = params['pattern']
        depth = params.get('depth', 2)
        times = params.get('times', -1)

        # Parse pattern (e.g., "mymodule.MyClass.my_method")
        parts = pattern.split('.')
        if len(parts) < 2:
            return {
                'status': 'error',
                'error': 'Pattern must be at least module.function'
            }

        # Find the target function/method
        try:
            target = self._resolve_target(pattern)
            if target is None:
                return {
                    'status': 'error',
                    'error': f'Cannot find target: {pattern}'
                }

            # Install watch
            watch_id = f"watch_{len(self.watches)}"
            self.watches[watch_id] = {
                'pattern': pattern,
                'target': target,
                'depth': depth,
                'times': times,
                'count': 0,
                'results': []
            }

            return {
                'status': 'success',
                'watch_id': watch_id,
                'message': f'Started watching {pattern}',
                'note': 'Watch simulation - actual tracing requires sys.settrace or instrumentation'
            }

        except Exception as e:
            return {
                'status': 'error',
                'error': f'Failed to start watch: {str(e)}'
            }

    def _stop_watch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop watching"""
        watch_id = params.get('watch_id')

        if watch_id and watch_id in self.watches:
            watch_info = self.watches.pop(watch_id)
            return {
                'status': 'success',
                'message': f'Stopped watch {watch_id}',
                'count': watch_info['count']
            }
        elif watch_id:
            return {
                'status': 'error',
                'error': f'Watch not found: {watch_id}'
            }
        else:
            # Stop all watches
            count = len(self.watches)
            self.watches.clear()
            return {
                'status': 'success',
                'message': f'Stopped {count} watches'
            }

    def _get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get status of active watches"""
        watches_info = []
        for watch_id, info in self.watches.items():
            watches_info.append({
                'id': watch_id,
                'pattern': info['pattern'],
                'count': info['count'],
                'times': info['times']
            })

        return {
            'status': 'success',
            'watches': watches_info,
            'total': len(watches_info)
        }

    def _resolve_target(self, pattern: str) -> Optional[Any]:
        """
        Resolve pattern to actual Python object
        
        Args:
            pattern: Dotted pattern like 'module.Class.method'
            
        Returns:
            The resolved object or None
        """
        parts = pattern.split('.')

        # Try to import module
        obj = None
        for i in range(len(parts), 0, -1):
            module_name = '.'.join(parts[:i])
            try:
                obj = __import__(module_name, fromlist=[''])
                remaining = parts[i:]
                break
            except (ImportError, ModuleNotFoundError):
                continue

        if obj is None:
            return None

        # Traverse remaining parts
        for part in remaining:
            try:
                obj = getattr(obj, part)
            except AttributeError:
                return None

        return obj

    def capture_call(self, watch_id: str, args: tuple, kwargs: dict, result: Any, duration: float):
        """
        Capture a function call (would be called by instrumentation)
        
        This is a placeholder - actual implementation would use sys.settrace
        or bytecode instrumentation
        """
        if watch_id not in self.watches:
            return

        watch_info = self.watches[watch_id]
        depth = watch_info['depth']

        # Format call information
        call_info = {
            'timestamp': time.time(),
            'args': format_value(args, depth),
            'kwargs': format_value(kwargs, depth),
            'result': format_value(result, depth),
            'duration': f'{duration:.6f}s'
        }

        watch_info['results'].append(call_info)
        watch_info['count'] += 1

        # Check if we should stop watching
        if watch_info['times'] > 0 and watch_info['count'] >= watch_info['times']:
            self.watches.pop(watch_id)
