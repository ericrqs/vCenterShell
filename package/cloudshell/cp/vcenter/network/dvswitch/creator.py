# -*- coding: utf-8 -*-
from threading import Lock
from time import sleep

from pyVmomi import vim


class DvPortGroupCreator(object):
    def __init__(self, pyvmomi_service, synchronous_task_waiter):
        """

        :param pyvmomi_service:
        :param synchronous_task_waiter:
        :type synchronous_task_waiter: cloudshell.cp.vcenter.common.vcenter.task_waiter.SynchronousTaskWaiter
        :return:
        """
        self.pyvmomi_service = pyvmomi_service
        self.synchronous_task_waiter = synchronous_task_waiter
        self._lock = Lock()

    def get_or_create_network(self,
                              si,
                              vm,
                              dv_port_name,
                              dv_switch_name,
                              dv_switch_path,
                              vlan_id,
                              vlan_spec,
                              logger,
                              promiscuous_mode):
        network = None
        error = None
        self._lock.acquire()
        try:
            # check if the network is attached to the vm and gets it, the function doesn't goes to the vcenter
            network = self.pyvmomi_service.get_network_by_name_from_vm(vm, dv_port_name)

            # if we didn't found the network on the vm
            if network is None:
                # try to get it from the vcenter
                try:
                    network = self.pyvmomi_service.find_portgroup(si,
                                                                  '{0}/{1}'.format(dv_switch_path, dv_switch_name),
                                                                  dv_port_name)
                except KeyError:
                    logger.debug("Failed to find port group for {}".format(dv_port_name), exc_info=True)
                    network = None

            # try to find it as a standard vswitch network on the host where the VM is running
            if network is None:
                for n in vm.runtime.host.network:
                    if n.name == dv_port_name:
                        network = n
                        break
                else:
                    logger.debug("Failed to find {} as a standard network".format(dv_port_name))

            # if we still couldn't get the network ---> create it(can't find it, play god!)
            if network is None:
                # if dvswitch name is actually a standard vswitch on the host where the VM is running
                if [vs for vs in vm.runtime.host.config.network.vswitch if vs.name == dv_switch_name]:
                    network = self._create_standard_portgroup_on_host(vm.runtime.host,
                                                                      dv_switch_name,
                                                                      dv_port_name,
                                                                      vlan_spec,
                                                                      vlan_id,
                                                                      promiscuous_mode,
                                                                      logger)
                else:
                    self._create_dv_port_group(dv_port_name,
                                               dv_switch_name,
                                               dv_switch_path,
                                               si,
                                               vlan_spec,
                                               vlan_id,
                                               logger,
                                               promiscuous_mode)
                network = self.pyvmomi_service.find_network_by_name(si, dv_switch_path, dv_port_name)

            if not network:
                raise ValueError('Could not get or create vlan named: {0}'.format(dv_port_name))
        except ValueError as e:
            logger.debug("Failed to find network", exc_info=True)
            error = e
        finally:
            self._lock.release()
            if error:
                raise error
            return network

    def _create_standard_portgroup_on_host(self, host, vswitchName, portgroupName, vlan_spec, vlan_id, promiscuous, logger):
        portgroup_spec = vim.host.PortGroup.Specification()
        portgroup_spec.vswitchName = vswitchName
        portgroup_spec.name = portgroupName
        if 'VlanIdSpec' in str(type(vlan_spec)):
            portgroup_spec.vlanId = vlan_id
        else:
            portgroup_spec.vlanId = 4095
        network_policy = vim.host.NetworkPolicy()
        network_policy.security = vim.host.NetworkPolicy.SecurityPolicy()
        network_policy.security.allowPromiscuous = str(promiscuous).lower() == 'true'
        network_policy.security.macChanges = False
        network_policy.security.forgedTransmits = False
        portgroup_spec.policy = network_policy
        host.configManager.networkSystem.AddPortGroup(portgroup_spec)
        for _ in range(20):
            sleep(3)
            for network in host.network:
                if network.name == portgroupName:
                    return network
        logger.debug('_create_standard_portgroup_on_host failed to find portgroup within 1 minute after creation')
        raise Exception('_create_standard_portgroup_on_host failed to find portgroup within 1 minute after creation')

    def _create_dv_port_group(self, dv_port_name, dv_switch_name, dv_switch_path, si, spec, vlan_id,
                              logger, promiscuous_mode):
        dv_switch = self.pyvmomi_service.get_folder(si, '{0}/{1}'.format(dv_switch_path, dv_switch_name))
        if not dv_switch:
            raise ValueError('DV Switch {0} not found in path {1}'.format(dv_switch_name, dv_switch_path))

        task = DvPortGroupCreator.dv_port_group_create_task(dv_port_name, dv_switch, spec, vlan_id,
                                                            logger, promiscuous_mode)
        self.synchronous_task_waiter.wait_for_task(task=task,
                                                   logger=logger,
                                                   action_name='Create dv port group',
                                                   hide_result=False)

    @staticmethod
    def dv_port_group_create_task(dv_port_name, dv_switch, spec, vlan_id, logger, promiscuous_mode, num_ports=32):
        """
        Create ' Distributed Virtual Portgroup' Task
        :param dv_port_name: <str>  Distributed Virtual Portgroup Name
        :param dv_switch: <vim.dvs.VmwareDistributedVirtualSwitch> Switch this Portgroup will be belong to
        :param spec:
        :param vlan_id: <int>
        :param logger:
        :param num_ports: <int> number of ports in this Group
        :param promiscuous_mode <str> 'True' or 'False' turn on/off promiscuous mode for the port group
        :return: <vim.Task> Task which really provides update
        """

        dv_pg_spec = vim.dvs.DistributedVirtualPortgroup.ConfigSpec()
        dv_pg_spec.name = dv_port_name
        dv_pg_spec.numPorts = num_ports
        dv_pg_spec.type = vim.dvs.DistributedVirtualPortgroup.PortgroupType.earlyBinding

        dv_pg_spec.defaultPortConfig = vim.dvs.VmwareDistributedVirtualSwitch.VmwarePortConfigPolicy()
        dv_pg_spec.defaultPortConfig.securityPolicy = vim.dvs.VmwareDistributedVirtualSwitch.SecurityPolicy()

        dv_pg_spec.defaultPortConfig.vlan = spec
        dv_pg_spec.defaultPortConfig.vlan.vlanId = vlan_id

        promiscuous_mode = promiscuous_mode.lower() == 'true'
        dv_pg_spec.defaultPortConfig.securityPolicy.allowPromiscuous = vim.BoolPolicy(value=promiscuous_mode)
        dv_pg_spec.defaultPortConfig.securityPolicy.forgedTransmits = vim.BoolPolicy(value=True)

        dv_pg_spec.defaultPortConfig.vlan.inherited = False
        dv_pg_spec.defaultPortConfig.securityPolicy.macChanges = vim.BoolPolicy(value=False)
        dv_pg_spec.defaultPortConfig.securityPolicy.inherited = False

        task = dv_switch.AddDVPortgroup_Task([dv_pg_spec])

        logger.info(u"DV Port Group '{}' CREATE Task ...".format(dv_port_name))
        return task

    @staticmethod
    def dv_port_group_destroy_task(port_group):
        """
        Creates 'Destroy Distributed Virtual Portgroup' Task
        The current Portgoriup should be 'Unused' if you wanted this task will be successfully performed
        :param port_group: <vim.dvs.DistributedVirtualPortgroup>
        :return: <vim.Task> Task which really provides update
        """
        return port_group.Destroy()
