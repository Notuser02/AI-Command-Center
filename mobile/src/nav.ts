// Navigation types: root stack = bottom tabs + full-screen pushed screens.

import type { NavigatorScreenParams } from '@react-navigation/native';

export type MainTabsParamList = {
  Dashboard: undefined;
  Chat: undefined;
  Tasks: undefined;
  Settings: undefined;
};

export type RootStackParamList = {
  Main: NavigatorScreenParams<MainTabsParamList>;
  TaskDetail: { id: number };
  NewTask: undefined;
};

declare global {
  namespace ReactNavigation {
    interface RootParamList extends RootStackParamList {}
  }
}
