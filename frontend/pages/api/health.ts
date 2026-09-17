import type { NextApiRequest, NextApiResponse } from 'next';

interface HealthResponse {
  status: string;
  service: string;
  timestamp: string;
}

export default function handler(
  req: NextApiRequest,
  res: NextApiResponse<HealthResponse>
) {
  res.status(200).json({
    status: 'ok',
    service: 'frontend',
    timestamp: new Date().toISOString(),
  });
}