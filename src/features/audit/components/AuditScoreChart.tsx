import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface AuditScoreChartProps {
    score: number;
    maxScore: number;
}

export function AuditScoreChart({ score, maxScore }: AuditScoreChartProps) {
    const safeMaxScore = maxScore > 0 ? maxScore : 1;
    const safeScore = Math.min(Math.max(score, 0), safeMaxScore);
    const remaining = Math.max(0, safeMaxScore - safeScore);

    const scoreColor =
        safeScore >= safeMaxScore * 0.8
            ? 'var(--color-emerald-400, #34d399)'
            : safeScore >= safeMaxScore * 0.6
                ? 'var(--color-amber-400, #fbbf24)'
                : 'var(--color-red-400, #f87171)';
    const scoreTextClass =
        safeScore >= safeMaxScore * 0.8
            ? 'text-green-400'
            : safeScore >= safeMaxScore * 0.6
                ? 'text-yellow-400'
                : 'text-red-400';

    return (
        <div className="relative flex h-48 w-full min-w-0 items-center justify-center">
            <ResponsiveContainer width="100%" height="100%" minWidth={192} minHeight={192} debounce={50}>
                <PieChart>
                    <Pie
                        data={[
                            { name: 'Score', value: safeScore },
                            { name: 'Remaining', value: remaining },
                        ]}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={80}
                        startAngle={90}
                        endAngle={-270}
                        dataKey="value"
                        stroke="none"
                    >
                        <Cell key="score" fill={scoreColor} />
                        <Cell key="remaining" fill="var(--color-slate-600, #334155)" opacity={0.3} />
                    </Pie>
                </PieChart>
            </ResponsiveContainer>

            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <div className={`flex items-baseline gap-1 ${scoreTextClass}`}>
                    <span className="text-3xl font-bold tracking-tight">{((safeScore / safeMaxScore) * 10).toFixed(1)}</span>
                    <span className="text-sm font-medium opacity-70">/ 10</span>
                </div>
                <span className="text-[11px] text-slate-500 font-medium mt-1">Qualidade</span>
            </div>
        </div>
    );
}
