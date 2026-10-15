import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { FishermanWorkspace } from '../features/fisherman/FishermanWorkspace';
import { MarineMonitoringWorkspace } from '../features/marine-monitoring/MarineMonitoringWorkspace';
import { ProtectedAreasWorkspace } from '../features/protected-areas/ProtectedAreasWorkspace';
import { CoastalAuthorityWorkspace } from '../features/coastal-authority/CoastalAuthorityWorkspace';
import { DisasterManagementWorkspace } from '../features/disaster-management/DisasterManagementWorkspace';

export const AppRouter: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/fisherman" replace />} />
      <Route path="/fisherman" element={<FishermanWorkspace />} />
      <Route path="/marine-monitoring" element={<MarineMonitoringWorkspace />} />
      <Route path="/protected-areas" element={<ProtectedAreasWorkspace />} />
      <Route path="/coastal-authority" element={<CoastalAuthorityWorkspace />} />
      <Route path="/disaster-management" element={<DisasterManagementWorkspace />} />
      <Route path="*" element={<Navigate to="/fisherman" replace />} />
    </Routes>
  );
};
