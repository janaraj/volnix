import { computeGrade } from '@/lib/score-utils';

interface ScoreGradeProps {
  score: number;
}

export function ScoreGrade({ score }: ScoreGradeProps) {
  const grade = computeGrade(score);
  return <span className={`font-mono text-lg font-bold ${grade.colorClass}`}>{grade.label}</span>;
}
