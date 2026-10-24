// App root: providers (Settings → Live) + navigation (tabs + pushed screens).

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text } from 'react-native';

import { SettingsProvider } from './src/context/SettingsContext';
import { LiveProvider } from './src/context/LiveContext';
import { colors } from './src/theme';
import type { MainTabsParamList, RootStackParamList } from './src/nav';

import DashboardScreen from './src/screens/DashboardScreen';
import ChatScreen from './src/screens/ChatScreen';
import TasksScreen, { NewTaskScreen } from './src/screens/TasksScreen';
import TaskDetailScreen from './src/screens/TaskDetailScreen';
import SettingsScreen from './src/screens/SettingsScreen';

const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: colors.bg,
    card: colors.panel,
    text: colors.text,
    border: colors.border,
    primary: colors.cyan,
  },
};

const Tab = createBottomTabNavigator<MainTabsParamList>();
const Stack = createNativeStackNavigator<RootStackParamList>();

function TabIcon({ label, color }: { label: string; color: string }) {
  return <Text style={{ color, fontSize: 16 }}>{label}</Text>;
}

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.panel },
        headerTintColor: colors.cyan,
        tabBarStyle: { backgroundColor: colors.panel, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.cyan,
        tabBarInactiveTintColor: colors.dim,
      }}
    >
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{ tabBarIcon: ({ color }) => <TabIcon label="◉" color={color} /> }}
      />
      <Tab.Screen
        name="Chat"
        component={ChatScreen}
        options={{ tabBarIcon: ({ color }) => <TabIcon label="▣" color={color} /> }}
      />
      <Tab.Screen
        name="Tasks"
        component={TasksScreen}
        options={{ tabBarIcon: ({ color }) => <TabIcon label="≡" color={color} /> }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{ tabBarIcon: ({ color }) => <TabIcon label="⚙" color={color} /> }}
      />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <SettingsProvider>
      <LiveProvider>
        <NavigationContainer theme={navTheme}>
          <Stack.Navigator
            screenOptions={{
              headerStyle: { backgroundColor: colors.panel },
              headerTintColor: colors.cyan,
              contentStyle: { backgroundColor: colors.bg },
            }}
          >
            <Stack.Screen name="Main" component={MainTabs} options={{ headerShown: false }} />
            <Stack.Screen
              name="TaskDetail"
              component={TaskDetailScreen}
              options={({ route }) => ({ title: `Task #${(route.params as any).id}` })}
            />
            <Stack.Screen name="NewTask" component={NewTaskScreen} options={{ title: 'New Task' }} />
          </Stack.Navigator>
        </NavigationContainer>
      </LiveProvider>
      <StatusBar style="light" />
    </SettingsProvider>
  );
}
