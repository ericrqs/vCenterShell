import unittest
from mock import MagicMock, Mock
from vCenterShell.commands.CommandExecuterService import CommandExecuterService


class TestCommandExecuterService(unittest.TestCase):
    def test_connect_execute_was_called(self):
        # Arrange
        network_adapter_retriever_command = MagicMock()
        command_executer_service = CommandExecuterService(None, network_adapter_retriever_command, Mock(), Mock())

        # Act
        command_executer_service.connect()

        # Assert
        network_adapter_retriever_command.execute.assert_called_with()

    def test_destroyVirtualMachineCommand(self):
        network_adapter_retriever_command = None
        destroy_virtual_machine_command = MagicMock()
        command_executer_service = CommandExecuterService(None, network_adapter_retriever_command,
                                                          destroy_virtual_machine_command, Mock())

        command_executer_service.destroy()

        destroy_virtual_machine_command.execute.assert_called_with()

    def test_deploy_from_template_deploy(self):
        # arrange
        deploy_from_template = Mock()
        deploy_from_template.execute = Mock(return_value=True)
        command_executer_service = CommandExecuterService(None, None, None, deploy_from_template)

        # act
        command_executer_service.deploy()

        # assert
        self.assertTrue(deploy_from_template.execute.called)


