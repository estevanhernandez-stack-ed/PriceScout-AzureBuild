#!/usr/bin/env python3
"""
Git Work Time Estimator & Billing Calculator
Analyzes Git history to estimate work sessions and generate invoices.
Perfect for AI-assisted development where actual coding time != value delivered.
"""

import subprocess
import json
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List, Dict, Tuple
import argparse


class GitWorkEstimator:
    def __init__(self, repo_path: str = ".", author: str = None):
        self.repo_path = repo_path
        self.author = author
        self.session_gap_minutes = 60  # If commits are >60min apart, it's a new session
        
    def get_commits(self, since: str = None, until: str = None) -> List[Dict]:
        """Get commit history with timestamps and stats."""
        cmd = [
            "git", "log",
            "--all",
            "--numstat",
            "--date=iso",
            "--pretty=format:COMMIT_START%n%H%n%an%n%ae%n%ad%n%s"
        ]
        
        if self.author:
            cmd.extend(["--author", self.author])
        if since:
            cmd.extend(["--since", since])
        if until:
            cmd.extend(["--until", until])
            
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.repo_path)
        
        commits = []
        current_commit = None
        
        for line in result.stdout.split('\n'):
            if line == 'COMMIT_START':
                if current_commit:
                    commits.append(current_commit)
                current_commit = {
                    'hash': None,
                    'author': None,
                    'email': None,
                    'date': None,
                    'message': None,
                    'files_changed': 0,
                    'insertions': 0,
                    'deletions': 0
                }
            elif current_commit:
                if current_commit['hash'] is None:
                    current_commit['hash'] = line
                elif current_commit['author'] is None:
                    current_commit['author'] = line
                elif current_commit['email'] is None:
                    current_commit['email'] = line
                elif current_commit['date'] is None:
                    current_commit['date'] = datetime.fromisoformat(line.strip())
                elif current_commit['message'] is None:
                    current_commit['message'] = line
                elif line.strip() and '\t' in line:
                    # Parse numstat line
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        added = parts[0]
                        deleted = parts[1]
                        if added != '-' and deleted != '-':
                            current_commit['insertions'] += int(added)
                            current_commit['deletions'] += int(deleted)
                            current_commit['files_changed'] += 1
        
        if current_commit:
            commits.append(current_commit)
            
        return sorted(commits, key=lambda x: x['date'])
    
    def estimate_sessions(self, commits: List[Dict]) -> List[Dict]:
        """Estimate work sessions from commit patterns."""
        if not commits:
            return []
        
        sessions = []
        current_session = {
            'start': commits[0]['date'],
            'end': commits[0]['date'],
            'commits': [commits[0]],
            'estimated_minutes': 15  # Minimum time per commit
        }
        
        for i in range(1, len(commits)):
            prev_commit = commits[i-1]
            curr_commit = commits[i]
            
            time_gap = (curr_commit['date'] - prev_commit['date']).total_seconds() / 60
            
            if time_gap > self.session_gap_minutes:
                # New session - close current and start new
                sessions.append(current_session)
                current_session = {
                    'start': curr_commit['date'],
                    'end': curr_commit['date'],
                    'commits': [curr_commit],
                    'estimated_minutes': 15
                }
            else:
                # Same session - extend it
                current_session['end'] = curr_commit['date']
                current_session['commits'].append(curr_commit)
        
        sessions.append(current_session)
        
        # Refine session estimates based on commit complexity
        for session in sessions:
            total_changes = sum(c['insertions'] + c['deletions'] for c in session['commits'])
            total_files = sum(c['files_changed'] for c in session['commits'])
            
            # Base time: actual elapsed time between first and last commit
            elapsed = (session['end'] - session['start']).total_seconds() / 60
            
            # Add buffer time based on complexity
            complexity_buffer = min(
                30,  # Max 30 min buffer per session
                (total_changes / 100) * 5 +  # 5 min per 100 lines changed
                (total_files * 2)  # 2 min per file
            )
            
            # Add post-commit time (testing, review, etc.)
            post_commit_buffer = 15  # Assume 15 min after last commit
            
            session['estimated_minutes'] = max(
                15,  # Minimum 15 minutes
                elapsed + complexity_buffer + post_commit_buffer
            )
            
            session['total_changes'] = total_changes
            session['total_files'] = total_files
        
        return sessions
    
    def calculate_metrics(self, commits: List[Dict], sessions: List[Dict]) -> Dict:
        """Calculate overall project metrics."""
        if not commits:
            return {
                'total_commits': 0,
                'total_sessions': 0,
                'estimated_hours': 0,
                'total_insertions': 0,
                'total_deletions': 0,
                'net_lines': 0,
                'total_files': 0,
                'date_range': None,
                'commits_per_day': {},
                'avg_commits_per_session': 0,
                'productivity_score': 0,
                'ai_efficiency_multiplier': 1.0
            }
        
        total_minutes = sum(s['estimated_minutes'] for s in sessions)
        total_insertions = sum(c['insertions'] for c in commits)
        total_deletions = sum(c['deletions'] for c in commits)
        total_files = len(set(f for c in commits for f in range(c['files_changed'])))
        
        # Calculate commits per day
        commits_per_day = defaultdict(int)
        for commit in commits:
            date_key = commit['date'].strftime('%Y-%m-%d')
            commits_per_day[date_key] += 1
        
        # Productivity score: lines per hour (higher = more efficient with AI)
        lines_per_hour = (total_insertions + total_deletions) / max(1, total_minutes / 60)
        
        return {
            'total_commits': len(commits),
            'total_sessions': len(sessions),
            'estimated_hours': round(total_minutes / 60, 2),
            'total_insertions': total_insertions,
            'total_deletions': total_deletions,
            'net_lines': total_insertions - total_deletions,
            'total_files': total_files,
            'date_range': {
                'start': commits[0]['date'].strftime('%Y-%m-%d'),
                'end': commits[-1]['date'].strftime('%Y-%m-%d'),
                'days': (commits[-1]['date'] - commits[0]['date']).days + 1
            },
            'commits_per_day': dict(commits_per_day),
            'avg_commits_per_session': round(len(commits) / len(sessions), 2),
            'productivity_score': round(lines_per_hour, 2),
            'ai_efficiency_multiplier': self._calculate_ai_multiplier(lines_per_hour)
        }
    
    def _calculate_ai_multiplier(self, lines_per_hour: float) -> float:
        """
        Calculate efficiency multiplier based on productivity.
        Traditional coding: ~50-100 lines/hour
        AI-assisted: 200-500+ lines/hour
        """
        if lines_per_hour < 100:
            return 1.0  # Traditional pace
        elif lines_per_hour < 200:
            return 1.5  # Light AI assistance
        elif lines_per_hour < 400:
            return 2.0  # Heavy AI assistance
        else:
            return 3.0  # AI-powered "vibe coding"
    
    def calculate_billing(
        self,
        metrics: Dict,
        hourly_rate: float = 150,
        project_rate: float = None,
        ai_premium: bool = True
    ) -> Dict:
        """
        Calculate billing with options for hourly or project-based pricing.
        
        Args:
            hourly_rate: Base hourly rate (default $150)
            project_rate: Fixed project price (overrides hourly)
            ai_premium: Whether to apply premium for high-efficiency AI work
        """
        estimated_hours = metrics['estimated_hours']
        
        if project_rate:
            # Project-based pricing
            effective_rate = project_rate / max(1, estimated_hours)
            return {
                'billing_type': 'project',
                'project_rate': project_rate,
                'estimated_hours': estimated_hours,
                'effective_hourly_rate': round(effective_rate, 2),
                'total': project_rate,
                'ai_efficiency_note': f"Completed in {estimated_hours}h vs traditional {estimated_hours * metrics['ai_efficiency_multiplier']:.1f}h estimate"
            }
        else:
            # Hourly pricing with AI premium
            base_total = estimated_hours * hourly_rate
            
            if ai_premium and metrics['productivity_score'] > 200:
                # Apply premium for high-efficiency work
                premium_multiplier = min(1.5, metrics['ai_efficiency_multiplier'] * 0.5)
                premium_total = base_total * premium_multiplier
                
                return {
                    'billing_type': 'hourly_with_ai_premium',
                    'estimated_hours': estimated_hours,
                    'base_hourly_rate': hourly_rate,
                    'premium_multiplier': round(premium_multiplier, 2),
                    'effective_hourly_rate': round(hourly_rate * premium_multiplier, 2),
                    'base_total': round(base_total, 2),
                    'premium_total': round(premium_total, 2),
                    'total': round(premium_total, 2),
                    'justification': f"AI-assisted development: {metrics['productivity_score']:.0f} lines/hour vs traditional ~75 lines/hour"
                }
            else:
                return {
                    'billing_type': 'hourly',
                    'estimated_hours': estimated_hours,
                    'hourly_rate': hourly_rate,
                    'total': round(base_total, 2)
                }
    
    def generate_report(
        self,
        since: str = None,
        until: str = None,
        hourly_rate: float = 150,
        project_rate: float = None,
        output_format: str = "text"
    ) -> str:
        """Generate a comprehensive work report."""
        commits = self.get_commits(since, until)
        sessions = self.estimate_sessions(commits)
        metrics = self.calculate_metrics(commits, sessions)
        billing = self.calculate_billing(metrics, hourly_rate, project_rate)
        
        if output_format == "json":
            return json.dumps({
                'metrics': metrics,
                'billing': billing,
                'sessions': [{
                    'start': s['start'].isoformat(),
                    'end': s['end'].isoformat(),
                    'estimated_minutes': s['estimated_minutes'],
                    'commits': len(s['commits']),
                    'changes': s['total_changes']
                } for s in sessions]
            }, indent=2)
        
        # Text format
        report = []
        report.append("=" * 80)
        report.append("GIT WORK TIME ESTIMATE & BILLING REPORT")
        report.append("=" * 80)
        report.append("")
        
        if self.author:
            report.append(f"Author: {self.author}")
        
        if metrics['date_range']:
            report.append(f"Period: {metrics['date_range']['start']} to {metrics['date_range']['end']}")
            report.append(f"Duration: {metrics['date_range']['days']} days")
        report.append("")
        
        report.append("DEVELOPMENT METRICS")
        report.append("-" * 80)
        report.append(f"Total Commits:        {metrics['total_commits']}")
        report.append(f"Work Sessions:        {metrics['total_sessions']}")
        report.append(f"Estimated Hours:      {metrics['estimated_hours']:.2f}h")
        report.append(f"Avg Session:          {metrics['estimated_hours']/max(1, metrics['total_sessions']):.2f}h")
        report.append("")
        report.append(f"Lines Added:          +{metrics['total_insertions']:,}")
        report.append(f"Lines Removed:        -{metrics['total_deletions']:,}")
        report.append(f"Net Lines:            {metrics['net_lines']:+,}")
        report.append(f"Files Modified:       ~{metrics['total_files']}")
        report.append("")
        report.append(f"Productivity:         {metrics['productivity_score']:.0f} lines/hour")
        report.append(f"AI Efficiency:        {metrics['ai_efficiency_multiplier']:.1f}x traditional pace")
        report.append("")
        
        report.append("BILLING SUMMARY")
        report.append("-" * 80)
        
        if billing['billing_type'] == 'project':
            report.append(f"Billing Type:         Project-Based")
            report.append(f"Project Rate:         ${billing['project_rate']:,.2f}")
            report.append(f"Time Invested:        {billing['estimated_hours']:.2f}h")
            report.append(f"Effective Rate:       ${billing['effective_hourly_rate']:,.2f}/hour")
            report.append("")
            report.append(f"TOTAL:                ${billing['total']:,.2f}")
            report.append("")
            report.append(f"Note: {billing['ai_efficiency_note']}")
        
        elif billing['billing_type'] == 'hourly_with_ai_premium':
            report.append(f"Billing Type:         Hourly + AI Premium")
            report.append(f"Base Rate:            ${billing['base_hourly_rate']:.2f}/hour")
            report.append(f"Premium Multiplier:   {billing['premium_multiplier']}x")
            report.append(f"Effective Rate:       ${billing['effective_hourly_rate']:.2f}/hour")
            report.append("")
            report.append(f"Base Total:           ${billing['base_total']:,.2f}")
            report.append(f"With AI Premium:      ${billing['premium_total']:,.2f}")
            report.append("")
            report.append(f"TOTAL:                ${billing['total']:,.2f}")
            report.append("")
            report.append(f"Justification: {billing['justification']}")
        
        else:
            report.append(f"Billing Type:         Hourly")
            report.append(f"Hourly Rate:          ${billing['hourly_rate']:.2f}/hour")
            report.append(f"Hours:                {billing['estimated_hours']:.2f}h")
            report.append("")
            report.append(f"TOTAL:                ${billing['total']:,.2f}")
        
        report.append("")
        report.append("=" * 80)
        report.append("")
        
        # Top 10 most productive sessions
        top_sessions = sorted(sessions, key=lambda s: s['total_changes'], reverse=True)[:10]
        if top_sessions:
            report.append("TOP 10 MOST PRODUCTIVE SESSIONS")
            report.append("-" * 80)
            for i, session in enumerate(top_sessions, 1):
                report.append(
                    f"{i:2}. {session['start'].strftime('%Y-%m-%d %H:%M')} | "
                    f"{session['estimated_minutes']:.0f}min | "
                    f"{session['total_changes']:,} lines | "
                    f"{len(session['commits'])} commits"
                )
            report.append("")
        
        return '\n'.join(report)


def main():
    parser = argparse.ArgumentParser(
        description='Estimate work time and calculate billing from Git history'
    )
    parser.add_argument('--author', help='Filter by author name/email')
    parser.add_argument('--since', help='Start date (e.g., "2025-01-01", "2 weeks ago")')
    parser.add_argument('--until', help='End date')
    parser.add_argument('--hourly-rate', type=float, default=150, help='Hourly rate (default: $150)')
    parser.add_argument('--project-rate', type=float, help='Fixed project rate (overrides hourly)')
    parser.add_argument('--no-ai-premium', action='store_true', help='Disable AI efficiency premium')
    parser.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    parser.add_argument('--repo', default='.', help='Repository path (default: current directory)')
    
    args = parser.parse_args()
    
    estimator = GitWorkEstimator(repo_path=args.repo, author=args.author)
    
    report = estimator.generate_report(
        since=args.since,
        until=args.until,
        hourly_rate=args.hourly_rate,
        project_rate=args.project_rate,
        output_format=args.format
    )
    
    print(report)


if __name__ == '__main__':
    main()
